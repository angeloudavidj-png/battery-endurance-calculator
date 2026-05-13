"""
endurance.py
============
Parametric rotorcraft endurance & range model.
  v1: rotor momentum theory only.
  v2: + rotor profile drag (induced + profile decomposition).
  v3: + wing-borne cruise mode for eVTOLs (induced drag + parasite drag).

Physical basis
--------------
ROTOR-BORNE MODE (multirotors, hover, transition):
Rotor shaft power splits into INDUCED (Glauert) + PROFILE (blade friction):

    P_induced_ideal = T * sqrt(T / (2 * rho * A))
    P_shaft         = P_induced_ideal / FoM_induced + profile_power_W
    P_electrical    = P_shaft / eta_drivetrain

WING-BORNE MODE (eVTOLs in cruise, V > V_stall):
Wing supports the aircraft, rotors act as conventional thrust propellers:

    CL  = W / (0.5 * rho * V^2 * S)
    CD  = Cd0 + CL^2 / (pi * AR * e)             (drag polar)
    D   = 0.5 * rho * V^2 * S * CD
    T   = D                                       (level cruise)
    P_shaft_cruise = T * V / eta_prop
    P_electrical    = P_shaft_cruise / eta_drivetrain

If wing_area_m2 = 0 (multirotor), only the rotor-borne model is used.
If wing_area_m2 > 0 (eVTOL), forward-flight power is min(P_rotor, P_wing),
with a stall guard: if the wing would need CL > CL_max, only the rotor
model is valid at that speed.

The min() blend captures the physical reality that the aircraft uses
whichever mode is more efficient. Below V_stall the wing can't support W,
so the rotor model wins. Above V_stall the wing is dramatically more
efficient, so the wing model wins. The crossover happens naturally.

Author: D. Angelou
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --- Physical constants ---------------------------------------------------
G = 9.80665                  # m/s^2, standard gravity
RHO_SEA_LEVEL = 1.225        # kg/m^3, ISA sea level
T_SEA_LEVEL = 288.15         # K
P_SEA_LEVEL = 101325.0       # Pa
LAPSE_RATE = 0.0065          # K/m, troposphere
R_AIR = 287.05               # J/(kg.K)


# --- Atmosphere -----------------------------------------------------------

def air_density(altitude_m: float = 0.0, temperature_offset_c: float = 0.0) -> float:
    """ISA troposphere density at altitude with optional temperature offset."""
    T = T_SEA_LEVEL - LAPSE_RATE * altitude_m + temperature_offset_c
    p = P_SEA_LEVEL * (T / T_SEA_LEVEL) ** (G / (R_AIR * LAPSE_RATE))
    return p / (R_AIR * T)


# --- Battery model --------------------------------------------------------

def battery_usable_Wh(
    capacity_Ah: float,
    nominal_voltage_V: float,
    usable_fraction: float = 0.90,
    discharge_efficiency: float = 0.96,
) -> float:
    """Usable battery energy after derating for reserve and IR losses."""
    nameplate_Wh = capacity_Ah * nominal_voltage_V
    return nameplate_Wh * usable_fraction * discharge_efficiency


def battery_specific_energy(
    capacity_Ah: float,
    nominal_voltage_V: float,
    pack_mass_kg: float,
) -> float:
    """Pack-level specific energy in Wh/kg."""
    if pack_mass_kg <= 0:
        return float("nan")
    return (capacity_Ah * nominal_voltage_V) / pack_mass_kg


def battery_usable_Wh_with_sag(
    capacity_Ah: float,
    nominal_voltage_V: float,
    usable_fraction: float = 0.90,
    discharge_efficiency: float = 0.96,
    voltage_sag: float = 0.0,
    P_load_W: float = 0.0,
) -> float:
    """Usable energy with optional voltage-sag derating (v5).

    When voltage_sag = 0 (default), identical to battery_usable_Wh().
    Linear sag approximation: V_eff = V_nom * (1 - sag * load_fraction)
    where load_fraction = P_load / P_peak_2C.
    Ref: Plett, 'Battery Management Systems Vol II'.
    """
    nameplate_Wh = capacity_Ah * nominal_voltage_V
    if voltage_sag <= 0 or P_load_W <= 0:
        return nameplate_Wh * usable_fraction * discharge_efficiency
    P_peak_2C = 2.0 * capacity_Ah * nominal_voltage_V
    load_fraction = min(P_load_W / P_peak_2C, 1.0)
    sag_factor = 1.0 - voltage_sag * load_fraction
    return nameplate_Wh * sag_factor * usable_fraction * discharge_efficiency


# --- Hover power ----------------------------------------------------------

def hover_power_momentum_theory(
    mass_kg: float,
    n_rotors: int,
    rotor_diameter_m: float,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    # v5 parameters
    altitude_AGL_m: float = 10000.0,
    cooling_power_W: float = 0.0,
) -> float:
    """Electrical hover power: induced (Glauert/FoM) + profile, divided by eta_drive.

    v5 additions:
    - altitude_AGL_m: Cheeseman-Bennett ground effect. Default 10000 m (OGE).
      Ref: Cheeseman & Bennett 1955, Leishman sec 5.6.
    - cooling_power_W: constant electrical draw from cooling systems.
    """
    rho = air_density(altitude_m, temperature_offset_c)
    thrust_N = mass_kg * G
    disk_area_m2 = n_rotors * math.pi * (rotor_diameter_m / 2.0) ** 2

    p_induced_ideal = thrust_N * math.sqrt(thrust_N / (2.0 * rho * disk_area_m2))
    p_shaft = p_induced_ideal / figure_of_merit + profile_power_W
    p_electrical = p_shaft / drivetrain_efficiency

    # v5: Cheeseman-Bennett ground effect (reduces induced power near ground)
    rotor_radius = rotor_diameter_m / 2.0
    if 0 < altitude_AGL_m < 2.0 * rotor_radius:
        z_over_R = altitude_AGL_m / rotor_radius
        ge_factor = math.sqrt(1.0 - (rotor_radius / (4.0 * altitude_AGL_m)) ** 2)
        # Only the induced component benefits; reconstruct
        p_induced_electrical = (p_induced_ideal / figure_of_merit) / drivetrain_efficiency
        p_profile_electrical = profile_power_W / drivetrain_efficiency
        p_electrical = p_induced_electrical * ge_factor + p_profile_electrical

    # v5: cooling parasitic load
    p_electrical += cooling_power_W

    return p_electrical


def hover_power_disk_loading(
    mass_kg: float,
    disk_loading_Nm2: float,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    cooling_power_W: float = 0.0,
) -> float:
    """Hover power using disk loading. Same model as the geometry version."""
    rho = air_density(altitude_m, temperature_offset_c)
    thrust_N = mass_kg * G
    p_induced_ideal = thrust_N * math.sqrt(disk_loading_Nm2 / (2.0 * rho))
    p_shaft = p_induced_ideal / figure_of_merit + profile_power_W
    p_electrical = p_shaft / drivetrain_efficiency + cooling_power_W
    return p_electrical


# --- Forward flight power -------------------------------------------------

def _glauert_induced_velocity(
    thrust_N: float,
    airspeed_mps: float,
    alpha_rad: float,
    rho: float,
    disk_area_m2: float,
    tol: float = 1e-4,
    max_iter: int = 200,
) -> float:
    """Solve Glauert's induced-velocity equation by fixed-point iteration."""
    vi_hover = math.sqrt(thrust_N / (2.0 * rho * disk_area_m2))
    vi = vi_hover
    omega = 0.5
    Vh = airspeed_mps * math.cos(alpha_rad)
    Vv = airspeed_mps * math.sin(alpha_rad)
    for _ in range(max_iter):
        denom = 2.0 * rho * disk_area_m2 * math.sqrt(Vh * Vh + (Vv + vi) ** 2)
        if denom <= 0:
            break
        vi_new = thrust_N / denom
        if abs(vi_new - vi) < tol:
            return vi_new
        vi = (1 - omega) * vi + omega * vi_new
    return vi


def forward_flight_power(
    mass_kg: float,
    airspeed_mps: float,
    n_rotors: int,
    rotor_diameter_m: float,
    Cd_body: float = 1.0,
    frontal_area_m2: float = 0.04,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    # v3: optional wing parameters. wing_area_m2 = 0 -> rotor-only (v2 behavior).
    wing_area_m2: float = 0.0,
    wing_span_m: float = 0.0,
    Cd0: float = 0.030,
    oswald_e: float = 0.80,
    CL_max: float = 1.3,
    prop_efficiency: float = 0.85,
    # v5 parameters
    transition_width_mps: float = 0.0,
    profile_K_mu: float = 0.0,
    rotor_tip_speed_mps: float = 200.0,
    cooling_power_W: float = 0.0,
) -> float:
    """Electrical forward-flight power at trimmed level flight.

    v5 additions:
    - transition_width_mps: sigmoid blend width around V_stall (0 = hard min).
    - profile_K_mu, rotor_tip_speed_mps: advance-ratio profile scaling.
    - cooling_power_W: constant electrical draw from cooling systems.
    """
    p_rotor = rotor_borne_forward_power(
        mass_kg, airspeed_mps, n_rotors, rotor_diameter_m,
        Cd_body, frontal_area_m2,
        figure_of_merit, drivetrain_efficiency, profile_power_W,
        altitude_m, temperature_offset_c,
        profile_K_mu=profile_K_mu,
        rotor_tip_speed_mps=rotor_tip_speed_mps,
        cooling_power_W=cooling_power_W,
    )
    if wing_area_m2 <= 0 or wing_span_m <= 0 or airspeed_mps <= 0:
        return p_rotor

    p_wing = wing_borne_cruise_power(
        mass_kg, airspeed_mps,
        wing_area_m2, wing_span_m,
        Cd0, oswald_e, CL_max, prop_efficiency,
        drivetrain_efficiency,
        altitude_m, temperature_offset_c,
        cooling_power_W=cooling_power_W,
    )

    # v5: sigmoid blend around V_stall instead of hard min()
    if transition_width_mps > 0:
        V_stall_val = stall_speed(mass_kg, wing_area_m2, CL_max,
                                  altitude_m, temperature_offset_c)
        alpha = 1.0 / (1.0 + math.exp(-(airspeed_mps - V_stall_val)
                                        / transition_width_mps))
        # If wing is stalled (p_wing=inf), compute an unclamped wing power
        # for blending: drag polar is still valid, just CL > CL_max.
        # The sigmoid ensures alpha ≈ 0 well below stall, so this
        # unphysical region has negligible weight.
        if math.isinf(p_wing):
            rho = air_density(altitude_m, temperature_offset_c)
            W = mass_kg * G
            AR = wing_span_m ** 2 / wing_area_m2
            q = 0.5 * rho * airspeed_mps ** 2
            if q > 0:
                CL_unclamped = W / (q * wing_area_m2)
                CD = Cd0 + CL_unclamped ** 2 / (math.pi * AR * oswald_e)
                D = q * wing_area_m2 * CD
                p_wing = (D * airspeed_mps / prop_efficiency) / drivetrain_efficiency + cooling_power_W
            else:
                return p_rotor
        return (1.0 - alpha) * p_rotor + alpha * p_wing

    return min(p_rotor, p_wing)


def rotor_borne_forward_power(
    mass_kg: float,
    airspeed_mps: float,
    n_rotors: int,
    rotor_diameter_m: float,
    Cd_body: float = 1.0,
    frontal_area_m2: float = 0.04,
    figure_of_merit: float = 0.65,
    drivetrain_efficiency: float = 0.78,
    profile_power_W: float = 0.0,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    # v5 parameters
    profile_K_mu: float = 0.0,
    rotor_tip_speed_mps: float = 200.0,
    cooling_power_W: float = 0.0,
) -> float:
    """Pure rotor-borne forward flight (v2 model, no wing).

    v5: profile power scales with advance ratio mu = V / V_tip:
        P_profile(V) = P_profile_hover * (1 + K_mu * mu^2)
    Ref: Leishman, Helicopter Aerodynamics 2nd ed, sec 5.4.
    """
    rho = air_density(altitude_m, temperature_offset_c)
    W = mass_kg * G
    A = n_rotors * math.pi * (rotor_diameter_m / 2.0) ** 2

    D = 0.5 * rho * airspeed_mps ** 2 * Cd_body * frontal_area_m2
    T = math.sqrt(W * W + D * D)
    alpha = math.atan2(D, W)

    vi = _glauert_induced_velocity(T, airspeed_mps, alpha, rho, A)
    p_induced_ideal = T * (airspeed_mps * math.sin(alpha) + vi)

    # v5: advance-ratio scaling of profile power
    if profile_K_mu > 0 and rotor_tip_speed_mps > 0:
        mu = airspeed_mps / rotor_tip_speed_mps
        profile_effective = profile_power_W * (1.0 + profile_K_mu * mu ** 2)
    else:
        profile_effective = profile_power_W

    p_shaft = p_induced_ideal / figure_of_merit + profile_effective
    p_electrical = p_shaft / drivetrain_efficiency + cooling_power_W
    return p_electrical


def wing_borne_cruise_power(
    mass_kg: float,
    airspeed_mps: float,
    wing_area_m2: float,
    wing_span_m: float,
    Cd0: float,
    oswald_e: float,
    CL_max: float,
    prop_efficiency: float,
    drivetrain_efficiency: float,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    cooling_power_W: float = 0.0,
) -> float:
    """Wing-borne cruise power for an eVTOL or fixed-wing aircraft.

    If the wing would need CL > CL_max, returns +inf (stalled).
    v5: cooling_power_W added on top of propulsion power.
    """
    rho = air_density(altitude_m, temperature_offset_c)
    W = mass_kg * G
    AR = wing_span_m ** 2 / wing_area_m2
    q = 0.5 * rho * airspeed_mps ** 2

    CL = W / (q * wing_area_m2)
    if CL > CL_max:
        return float("inf")  # stall: wing cannot generate enough lift

    CD = Cd0 + CL ** 2 / (math.pi * AR * oswald_e)
    D = q * wing_area_m2 * CD
    T = D  # level flight

    p_shaft = T * airspeed_mps / prop_efficiency
    p_electrical = p_shaft / drivetrain_efficiency + cooling_power_W
    return p_electrical


def stall_speed(
    mass_kg: float,
    wing_area_m2: float,
    CL_max: float = 1.3,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> float:
    """Wing-only stall speed (level 1-g flight). Returns inf if no wing."""
    if wing_area_m2 <= 0:
        return float("inf")
    rho = air_density(altitude_m, temperature_offset_c)
    return math.sqrt(2 * mass_kg * G / (rho * wing_area_m2 * CL_max))


# --- Aircraft container ---------------------------------------------------

@dataclass
class Aircraft:
    """All parameters needed to evaluate endurance."""
    name: str
    mass_kg: float
    n_rotors: int
    rotor_diameter_m: float
    battery_capacity_Ah: float
    battery_voltage_V: float
    Cd_body: float = 1.0
    frontal_area_m2: float = 0.04
    figure_of_merit: float = 0.65         # induced-power efficiency (with profile_power_W > 0)
    drivetrain_efficiency: float = 0.78
    profile_power_W: float = 0.0          # rotor profile power at hover (v2)
    usable_fraction: float = 0.90
    discharge_efficiency: float = 0.96
    # v3: wing-borne cruise parameters. wing_area_m2 = 0 -> pure multirotor.
    wing_area_m2: float = 0.0
    wing_span_m: float = 0.0
    Cd0: float = 0.030
    oswald_e: float = 0.80
    CL_max: float = 1.3
    prop_efficiency: float = 0.85
    notes: str = ""
    # v5: physics extensions (all defaults preserve v4 behavior)
    transition_width_mps: float = 0.0       # A: sigmoid blend width (0 = hard min)
    profile_K_mu: float = 0.0               # B: advance-ratio scaling (0 = constant)
    rotor_tip_speed_mps: float = 200.0      # B: tip speed for mu calc
    voltage_sag_at_full_load: float = 0.0   # C: fractional sag (0 = none)
    cooling_power_W: float = 0.0            # E: constant cooling draw (0 = none)

    @property
    def nameplate_Wh(self) -> float:
        return self.battery_capacity_Ah * self.battery_voltage_V

    @property
    def disk_area_m2(self) -> float:
        return self.n_rotors * math.pi * (self.rotor_diameter_m / 2.0) ** 2

    @property
    def disk_loading_Nm2(self) -> float:
        return (self.mass_kg * G) / self.disk_area_m2

    @property
    def has_wing(self) -> bool:
        return self.wing_area_m2 > 0 and self.wing_span_m > 0

    @property
    def aspect_ratio(self) -> float:
        if not self.has_wing:
            return float("nan")
        return self.wing_span_m ** 2 / self.wing_area_m2

    @property
    def wing_loading_Nm2(self) -> float:
        if not self.has_wing:
            return float("nan")
        return (self.mass_kg * G) / self.wing_area_m2

    def vrs_descent_boundary_mps(
        self,
        altitude_m: float = 0.0,
        temperature_offset_c: float = 0.0,
    ) -> float:
        """Descent speed above which vortex ring state (VRS) is a concern.

        Standard boundary: V_descent > 0.5 * v_induced_hover.
        Ref: Leishman, Helicopter Aerodynamics 2nd ed, sec 2.13.4.
        Note: the endurance model assumes level flight, so VRS is an
        off-axis concern not actively modeled in the power calculations.
        """
        rho = air_density(altitude_m, temperature_offset_c)
        T = self.mass_kg * G
        A = self.disk_area_m2
        v_i_hover = math.sqrt(T / (2.0 * rho * A))
        return 0.5 * v_i_hover


# --- High-level endurance & range -----------------------------------------

def hover_endurance_min(
    ac: Aircraft,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    altitude_AGL_m: float = 10000.0,
) -> float:
    """Predicted hover endurance in minutes."""
    P = hover_power_momentum_theory(
        mass_kg=ac.mass_kg,
        n_rotors=ac.n_rotors,
        rotor_diameter_m=ac.rotor_diameter_m,
        figure_of_merit=ac.figure_of_merit,
        drivetrain_efficiency=ac.drivetrain_efficiency,
        profile_power_W=ac.profile_power_W,
        altitude_m=altitude_m,
        temperature_offset_c=temperature_offset_c,
        altitude_AGL_m=altitude_AGL_m,
        cooling_power_W=ac.cooling_power_W,
    )
    E = battery_usable_Wh_with_sag(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
        ac.voltage_sag_at_full_load, P,
    )
    return (E / P) * 60.0


def forward_endurance_and_range(
    ac: Aircraft,
    airspeed_mps: float,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    wind_headwind_mps: float = 0.0,
) -> tuple[float, float]:
    """Predicted endurance (min) and range (km) at a given cruise speed.

    v5: wind_headwind_mps adjusts ground speed for range calculation.
    Negative = tailwind = increases ground range.
    """
    P = forward_flight_power(
        mass_kg=ac.mass_kg,
        airspeed_mps=airspeed_mps,
        n_rotors=ac.n_rotors,
        rotor_diameter_m=ac.rotor_diameter_m,
        Cd_body=ac.Cd_body,
        frontal_area_m2=ac.frontal_area_m2,
        figure_of_merit=ac.figure_of_merit,
        drivetrain_efficiency=ac.drivetrain_efficiency,
        profile_power_W=ac.profile_power_W,
        altitude_m=altitude_m,
        temperature_offset_c=temperature_offset_c,
        wing_area_m2=ac.wing_area_m2,
        wing_span_m=ac.wing_span_m,
        Cd0=ac.Cd0,
        oswald_e=ac.oswald_e,
        CL_max=ac.CL_max,
        prop_efficiency=ac.prop_efficiency,
        transition_width_mps=ac.transition_width_mps,
        profile_K_mu=ac.profile_K_mu,
        rotor_tip_speed_mps=ac.rotor_tip_speed_mps,
        cooling_power_W=ac.cooling_power_W,
    )
    E = battery_usable_Wh_with_sag(
        ac.battery_capacity_Ah, ac.battery_voltage_V,
        ac.usable_fraction, ac.discharge_efficiency,
        ac.voltage_sag_at_full_load, P,
    )
    t_min = (E / P) * 60.0
    V_ground = airspeed_mps - wind_headwind_mps
    range_km = (V_ground * (t_min / 60.0)) * 3.6
    return t_min, range_km


def power_curve(
    ac: Aircraft,
    speeds_mps: list[float],
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
) -> list[float]:
    """Power-required curve over a range of airspeeds (W)."""
    out = []
    for V in speeds_mps:
        if V <= 0.1:
            out.append(hover_power_momentum_theory(
                mass_kg=ac.mass_kg,
                n_rotors=ac.n_rotors,
                rotor_diameter_m=ac.rotor_diameter_m,
                figure_of_merit=ac.figure_of_merit,
                drivetrain_efficiency=ac.drivetrain_efficiency,
                profile_power_W=ac.profile_power_W,
                altitude_m=altitude_m,
                temperature_offset_c=temperature_offset_c,
                cooling_power_W=ac.cooling_power_W,
            ))
        else:
            out.append(forward_flight_power(
                mass_kg=ac.mass_kg,
                airspeed_mps=V,
                n_rotors=ac.n_rotors,
                rotor_diameter_m=ac.rotor_diameter_m,
                Cd_body=ac.Cd_body,
                frontal_area_m2=ac.frontal_area_m2,
                figure_of_merit=ac.figure_of_merit,
                drivetrain_efficiency=ac.drivetrain_efficiency,
                profile_power_W=ac.profile_power_W,
                altitude_m=altitude_m,
                temperature_offset_c=temperature_offset_c,
                wing_area_m2=ac.wing_area_m2,
                wing_span_m=ac.wing_span_m,
                Cd0=ac.Cd0,
                oswald_e=ac.oswald_e,
                CL_max=ac.CL_max,
                prop_efficiency=ac.prop_efficiency,
                transition_width_mps=ac.transition_width_mps,
                profile_K_mu=ac.profile_K_mu,
                rotor_tip_speed_mps=ac.rotor_tip_speed_mps,
                cooling_power_W=ac.cooling_power_W,
            ))
    return out


def best_cruise_speed(
    ac: Aircraft,
    altitude_m: float = 0.0,
    temperature_offset_c: float = 0.0,
    v_min: float = 1.0,
    v_max: float = 30.0,
    n_pts: int = 201,
    wind_headwind_mps: float = 0.0,
) -> tuple[float, float, float]:
    """Find the airspeed that maximizes ground range.

    v5: wind_headwind_mps shifts the optimum via ground speed.
    """
    best_V = v_min
    best_range = -1.0
    best_t = 0.0
    step = (v_max - v_min) / max(n_pts - 1, 1)
    for i in range(n_pts):
        V = v_min + i * step
        t_min, rng_km = forward_endurance_and_range(
            ac, V, altitude_m, temperature_offset_c,
            wind_headwind_mps=wind_headwind_mps,
        )
        if rng_km > best_range:
            best_range = rng_km
            best_V = V
            best_t = t_min
    return best_V, best_range, best_t


# --- Self-test ------------------------------------------------------------

if __name__ == "__main__":
    test = Aircraft(
        name="Test 1 kg quad",
        mass_kg=1.0,
        n_rotors=4,
        rotor_diameter_m=0.254,
        battery_capacity_Ah=5.0,
        battery_voltage_V=14.8,
        figure_of_merit=0.87,
        drivetrain_efficiency=0.78,
        profile_power_W=30.0,
    )
    P = hover_power_momentum_theory(
        test.mass_kg, test.n_rotors, test.rotor_diameter_m,
        test.figure_of_merit, test.drivetrain_efficiency, test.profile_power_W,
    )
    t = hover_endurance_min(test)
    Vbest, rng, tcruise = best_cruise_speed(test)
    print(f"{test.name}")
    print(f"  Disk loading       : {test.disk_loading_Nm2:6.1f} N/m^2")
    print(f"  Hover power        : {P:6.1f} W")
    print(f"  Hover endurance    : {t:6.1f} min")
    print(f"  Best cruise speed  : {Vbest:6.1f} m/s")
    print(f"  Range at best V    : {rng:6.2f} km")
    print(f"  Endurance at best V: {tcruise:6.1f} min")
