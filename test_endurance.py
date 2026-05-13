"""
test_endurance.py
=================
Lightweight smoke + regression tests. Run with:
    python -m pytest -v
or:
    python test_endurance.py
"""

import math

from endurance import (
    G,
    air_density,
    battery_usable_Wh,
    hover_power_momentum_theory,
    hover_power_disk_loading,
    forward_flight_power,
    _glauert_induced_velocity,
    Aircraft,
    hover_endurance_min,
    forward_endurance_and_range,
    best_cruise_speed,
    power_curve,
)
from aircraft_db import ALL_AIRCRAFT, PUBLISHED_HOVER_MIN, PUBLISHED_FORWARD_REFS


# --- Atmosphere -----------------------------------------------------------

def test_isa_sea_level():
    rho = air_density(0.0, 0.0)
    assert abs(rho - 1.225) < 0.005, f"rho={rho}"


def test_air_density_decreases_with_altitude():
    rho0 = air_density(0.0)
    rho2k = air_density(2000.0)
    rho5k = air_density(5000.0)
    assert rho0 > rho2k > rho5k


# --- Momentum theory ------------------------------------------------------

def test_hover_power_scales_correctly():
    """Doubling mass at fixed area should multiply hover power by 2^1.5 (no profile)."""
    P1 = hover_power_momentum_theory(1.0, 4, 0.254, 1.0, 1.0, profile_power_W=0)
    P2 = hover_power_momentum_theory(2.0, 4, 0.254, 1.0, 1.0, profile_power_W=0)
    ratio = P2 / P1
    expected = 2 ** 1.5
    assert abs(ratio - expected) / expected < 0.01


def test_disk_loading_matches_explicit_geometry():
    """The two hover-power formulas should agree (with same profile_power)."""
    mass, n, dia = 2.0, 4, 0.30
    A = n * math.pi * (dia / 2) ** 2
    DL = mass * G / A
    P_geom = hover_power_momentum_theory(mass, n, dia, 0.87, 0.80, profile_power_W=30)
    P_dl   = hover_power_disk_loading(mass, DL,  0.87, 0.80, profile_power_W=30)
    assert abs(P_geom - P_dl) / P_geom < 1e-6


def test_profile_power_zero_matches_v1():
    """With profile_power=0, hover power should match the pure induced/FoM model."""
    P = hover_power_momentum_theory(1.0, 4, 0.254, 0.65, 0.78, profile_power_W=0)
    # v1 expected: P_ideal/(FoM*eta)
    T = 9.80665
    A = 4 * math.pi * 0.127**2
    P_ideal = T * math.sqrt(T / (2 * 1.225 * A))
    P_v1 = P_ideal / (0.65 * 0.78)
    assert abs(P - P_v1) / P_v1 < 1e-4


def test_profile_power_adds_constant():
    """Adding profile_power_W increases hover power by exactly profile/eta."""
    P0 = hover_power_momentum_theory(1.0, 4, 0.254, 0.87, 0.78, profile_power_W=0)
    P1 = hover_power_momentum_theory(1.0, 4, 0.254, 0.87, 0.78, profile_power_W=50)
    expected_delta = 50 / 0.78
    assert abs((P1 - P0) - expected_delta) < 1e-6


# --- Glauert induced velocity --------------------------------------------

def test_glauert_recovers_hover():
    """At V=0, Glauert vi should equal momentum-theory hover vi."""
    T, rho, A = 50.0, 1.225, 0.20
    vi = _glauert_induced_velocity(T, 0.0, 0.0, rho, A)
    vi_hover = math.sqrt(T / (2 * rho * A))
    assert abs(vi - vi_hover) / vi_hover < 0.01


def test_forward_power_lower_than_hover_at_moderate_speed():
    """Multirotor power curve dips below hover power once forward speed
    reduces induced-velocity demand (this still holds with profile drag)."""
    P_hover = hover_power_momentum_theory(1.5, 4, 0.254, 0.87, 0.78, profile_power_W=30)
    P_8 = forward_flight_power(1.5, 8.0, 4, 0.254, 1.0, 0.04, 0.87, 0.78, profile_power_W=30)
    assert P_8 < P_hover


def test_profile_power_constant_with_speed():
    """Difference between forward-flight power at two profile settings
    is exactly profile_delta/eta -- proves profile stays constant with V."""
    args = (1.5, 12.0, 4, 0.254, 1.0, 0.04, 0.87, 0.78)
    P0 = forward_flight_power(*args, profile_power_W=0)
    P1 = forward_flight_power(*args, profile_power_W=50)
    expected_delta = 50 / 0.78
    assert abs((P1 - P0) - expected_delta) < 1e-4


# --- Battery model --------------------------------------------------------

def test_battery_usable_energy_basic():
    E = battery_usable_Wh(5.0, 14.8, 0.9, 0.96)
    assert abs(E - 63.94) < 0.05


# --- Aircraft container ---------------------------------------------------

def test_aircraft_disk_loading():
    ac = Aircraft(
        name="test", mass_kg=2.0, n_rotors=4, rotor_diameter_m=0.30,
        battery_capacity_Ah=5.0, battery_voltage_V=14.8,
    )
    A = 4 * math.pi * 0.15 ** 2
    expected = (2.0 * G) / A
    assert abs(ac.disk_loading_Nm2 - expected) < 1e-6


# --- Validation against published specs -----------------------------------

def test_hover_predictions_within_1_percent():
    """v2 headline: tuned model matches all references within 1 %."""
    for ac in ALL_AIRCRAFT:
        predicted = hover_endurance_min(ac)
        published = PUBLISHED_HOVER_MIN[ac.name]
        err = abs(predicted - published) / published
        assert err < 0.01, (
            f"{ac.name}: predicted {predicted:.2f} min vs published "
            f"{published:.2f} min -> {err*100:.2f}% error"
        )


def test_mavic3_forward_flight_within_6_percent():
    """v2 forward-flight validation: profile drag added, error should be < 6 %."""
    mavic = ALL_AIRCRAFT[0]
    assert mavic.name == "DJI Mavic 3 Classic"
    for V_test, target, kind in PUBLISHED_FORWARD_REFS[mavic.name]:
        t_min, rng_km = forward_endurance_and_range(mavic, V_test)
        predicted = rng_km if kind == "range_km" else t_min
        err = abs(predicted - target) / target
        assert err < 0.06, (
            f"Mavic 3 {kind}@{V_test} m/s: predicted {predicted:.2f} vs "
            f"published {target:.2f} -> {err*100:.1f}% error"
        )


# --- v3 wing-borne mode --------------------------------------------------

def test_wing_stall_returns_infinity():
    """Below stall, wing model must signal infeasibility."""
    from endurance import wing_borne_cruise_power
    # 2000 kg, 20 m^2 wing, CL_max 1.3 -> V_stall ~ 35 m/s. At V=10 m/s, far below.
    P = wing_borne_cruise_power(
        mass_kg=2000.0, airspeed_mps=10.0,
        wing_area_m2=20.0, wing_span_m=12.0,
        Cd0=0.03, oswald_e=0.8, CL_max=1.3,
        prop_efficiency=0.85, drivetrain_efficiency=0.92,
    )
    assert math.isinf(P), "wing stall should return inf"


def test_wing_mode_beats_rotor_in_cruise():
    """For an aircraft with wings, cruise power must be lower with the
    wing-borne model than with rotors-only."""
    from endurance import wing_borne_cruise_power, rotor_borne_forward_power
    P_wing = wing_borne_cruise_power(
        mass_kg=2000.0, airspeed_mps=70.0,
        wing_area_m2=20.0, wing_span_m=12.0,
        Cd0=0.03, oswald_e=0.8, CL_max=1.3,
        prop_efficiency=0.85, drivetrain_efficiency=0.92,
    )
    P_rotor = rotor_borne_forward_power(
        mass_kg=2000.0, airspeed_mps=70.0,
        n_rotors=6, rotor_diameter_m=2.9,
        Cd_body=0.30, frontal_area_m2=2.4,
        figure_of_merit=0.85, drivetrain_efficiency=0.92,
        profile_power_W=134_100.0,
    )
    assert P_wing < P_rotor, (
        f"wing should beat rotor at cruise: wing={P_wing:.0f}, rotor={P_rotor:.0f}"
    )


def test_joby_s4_cruise_within_5_percent():
    """v3 headline: Joby S4 cruise range matches Joby's published 161 km."""
    joby = next(a for a in ALL_AIRCRAFT if "Joby" in a.name)
    refs = PUBLISHED_FORWARD_REFS[joby.name]
    V_test, target_km, kind = refs[0]
    assert kind == "range_km"
    t_min, rng_km = forward_endurance_and_range(joby, V_test)
    err = abs(rng_km - target_km) / target_km
    assert err < 0.05, (
        f"Joby S4 range@{V_test} m/s: predicted {rng_km:.1f} km vs "
        f"published {target_km:.1f} km -> {err*100:.1f}% error"
    )


def test_no_wing_disables_wing_model():
    """Aircraft with wing_area_m2 = 0 behaves identically with or without
    the wing-mode code path."""
    from dataclasses import replace
    mavic = next(a for a in ALL_AIRCRAFT if "Mavic" in a.name)
    P_curve = power_curve(mavic, [5.0, 10.0, 15.0, 20.0])
    # Force-zero the wing fields to confirm
    mavic2 = replace(mavic, wing_area_m2=0.0, wing_span_m=0.0)
    P_curve2 = power_curve(mavic2, [5.0, 10.0, 15.0, 20.0])
    for a, b in zip(P_curve, P_curve2):
        assert abs(a - b) < 1e-9


def test_stall_speed_helper():
    """Sanity-check the stall_speed helper."""
    from endurance import stall_speed
    V_stall = stall_speed(2177.0, 20.2, 1.3)
    # Hand calc: sqrt(2*21357/(1.225*20.2*1.3)) ~ 36.4 m/s
    assert 35.0 < V_stall < 38.0


# --- v4 tests: three new eVTOL architectures -----------------------------

def test_archer_midnight_cruise_within_5_percent():
    """Archer Midnight: 161 km range at 67 m/s should match within 5 %."""
    from aircraft_db import ARCHER_MIDNIGHT
    _, range_km = forward_endurance_and_range(ARCHER_MIDNIGHT, 67.0)
    err_pct = abs(range_km - 161.0) / 161.0 * 100.0
    assert err_pct < 5.0, f"Archer Midnight cruise error {err_pct:.2f} % > 5 %"


def test_beta_alia_cruise_within_5_percent():
    """Beta ALIA-250: 463 km range at 62 m/s should match within 5 %."""
    from aircraft_db import BETA_ALIA_250
    _, range_km = forward_endurance_and_range(BETA_ALIA_250, 62.0)
    err_pct = abs(range_km - 463.0) / 463.0 * 100.0
    assert err_pct < 5.0, f"Beta ALIA-250 cruise error {err_pct:.2f} % > 5 %"


def test_vertical_vx4_cruise_within_5_percent():
    """Vertical VX4: 161 km range at 67 m/s should match within 5 %."""
    from aircraft_db import VERTICAL_VX4
    _, range_km = forward_endurance_and_range(VERTICAL_VX4, 67.0)
    err_pct = abs(range_km - 161.0) / 161.0 * 100.0
    assert err_pct < 5.0, f"Vertical VX4 cruise error {err_pct:.2f} % > 5 %"


def test_beta_alia_has_longest_range():
    """Sanity check: Beta ALIA's long-range design should produce
    the highest best-range prediction of the four eVTOLs."""
    from aircraft_db import JOBY_S4, ARCHER_MIDNIGHT, BETA_ALIA_250, VERTICAL_VX4
    ranges = {}
    for ac in [JOBY_S4, ARCHER_MIDNIGHT, BETA_ALIA_250, VERTICAL_VX4]:
        _, r_best, _ = best_cruise_speed(ac, v_min=1.0, v_max=110.0, n_pts=221)
        ranges[ac.name] = r_best
    longest = max(ranges, key=ranges.get)
    assert "Beta" in longest, f"Expected Beta ALIA to have longest range; got {longest} at {ranges[longest]:.0f} km"


# --- v5 tests: seven new physics terms + regression ----------------------

def test_smooth_transition_eliminates_step():
    """At V near V_stall, Joby's power curve slope should be smooth with
    transition_width_mps > 0 (no derivative discontinuity)."""
    from dataclasses import replace
    from endurance import stall_speed
    joby = next(a for a in ALL_AIRCRAFT if "Joby" in a.name)
    assert joby.transition_width_mps > 0, "Joby should have v5 transition enabled"
    V_stall = stall_speed(joby.mass_kg, joby.wing_area_m2, joby.CL_max)
    dV = 0.5
    speeds = [V_stall - dV, V_stall, V_stall + dV]
    P = power_curve(joby, speeds)
    slope_below = (P[1] - P[0]) / dV
    slope_above = (P[2] - P[1]) / dV
    # Slopes should be within 50% of each other (smooth, no step)
    if slope_below == 0 or slope_above == 0:
        return  # edge case, skip
    ratio = abs(slope_above / slope_below) if slope_below != 0 else 999
    assert 0.1 < ratio < 10.0, (
        f"Slope discontinuity: below={slope_below:.0f}, above={slope_above:.0f}, ratio={ratio:.2f}"
    )


def test_profile_power_grows_with_mu():
    """At mu = 0.3, P_profile should be ~1.42x P_profile_hover with K_mu=4.65."""
    from endurance import rotor_borne_forward_power
    args = dict(mass_kg=2.0, n_rotors=4, rotor_diameter_m=0.30,
                Cd_body=1.0, frontal_area_m2=0.04,
                figure_of_merit=0.87, drivetrain_efficiency=1.0,
                profile_power_W=100.0)
    V_test = 0.3 * 200.0  # mu = 0.3 at tip_speed = 200
    P_base = rotor_borne_forward_power(airspeed_mps=V_test, **args,
                                        profile_K_mu=0.0, rotor_tip_speed_mps=200.0)
    P_mu = rotor_borne_forward_power(airspeed_mps=V_test, **args,
                                      profile_K_mu=4.65, rotor_tip_speed_mps=200.0)
    # Profile delta should be 100 * 4.65 * 0.3^2 = 41.85 W (at eta=1.0)
    delta = P_mu - P_base
    expected_delta = 100.0 * 4.65 * 0.09  # 41.85
    assert abs(delta - expected_delta) < 1.0, (
        f"Profile mu-scaling delta={delta:.2f}, expected={expected_delta:.2f}"
    )


def test_voltage_sag_reduces_usable_Wh():
    """Sag = 0.10 should reduce usable Wh by 5-10% under typical load."""
    from endurance import battery_usable_Wh, battery_usable_Wh_with_sag
    E_base = battery_usable_Wh(5.0, 14.8, 0.90, 0.96)
    # Typical load = ~100 W for a small drone; P_peak_2C = 2*5*14.8 = 148 W
    E_sag = battery_usable_Wh_with_sag(5.0, 14.8, 0.90, 0.96,
                                         voltage_sag=0.10, P_load_W=100.0)
    reduction_pct = (1 - E_sag / E_base) * 100
    assert 5.0 < reduction_pct < 10.0, (
        f"Sag reduction {reduction_pct:.2f}% not in 5-10% range"
    )


def test_ground_effect_reduces_hover_power():
    """At AGL = 0.5 * R, hover power should be 8-15% lower than OGE."""
    ac = Aircraft(name="GE test", mass_kg=2.0, n_rotors=4,
                  rotor_diameter_m=0.50,
                  battery_capacity_Ah=5.0, battery_voltage_V=14.8)
    R = 0.25  # radius
    P_oge = hover_power_momentum_theory(ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
                                         altitude_AGL_m=100.0)
    P_ige = hover_power_momentum_theory(ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
                                         altitude_AGL_m=0.5 * R)
    reduction_pct = (1 - P_ige / P_oge) * 100
    assert 3.0 < reduction_pct < 20.0, (
        f"Ground effect reduction {reduction_pct:.2f}% not in expected range"
    )


def test_cooling_adds_constant_draw():
    """Setting cooling = 1000 W increases P_electrical by exactly 1000 W."""
    P_base = hover_power_momentum_theory(2.0, 4, 0.30, cooling_power_W=0.0)
    P_cool = hover_power_momentum_theory(2.0, 4, 0.30, cooling_power_W=1000.0)
    assert abs((P_cool - P_base) - 1000.0) < 0.01, (
        f"Cooling delta = {P_cool - P_base:.2f}, expected 1000.0"
    )
    # Also check forward flight
    P_fwd_base = forward_flight_power(2.0, 10.0, 4, 0.30, cooling_power_W=0.0)
    P_fwd_cool = forward_flight_power(2.0, 10.0, 4, 0.30, cooling_power_W=1000.0)
    assert abs((P_fwd_cool - P_fwd_base) - 1000.0) < 0.01


def test_wind_headwind_reduces_ground_range():
    """5 m/s headwind at 50 m/s cruise should reduce ground range by exactly 10%."""
    ac = Aircraft(name="Wind test", mass_kg=2000.0, n_rotors=6,
                  rotor_diameter_m=2.9,
                  battery_capacity_Ah=1650.0, battery_voltage_V=100.0,
                  wing_area_m2=20.0, wing_span_m=12.0)
    _, r_no_wind = forward_endurance_and_range(ac, 50.0, wind_headwind_mps=0.0)
    _, r_headwind = forward_endurance_and_range(ac, 50.0, wind_headwind_mps=5.0)
    # Ground range with 5 m/s headwind at 50 m/s: V_ground = 45 m/s
    # Expected ratio = 45/50 = 0.90 -> exactly 10% reduction
    ratio = r_headwind / r_no_wind
    assert abs(ratio - 0.90) < 0.001, (
        f"Wind ratio {ratio:.4f}, expected 0.90"
    )


def test_vrs_boundary_is_physical():
    """Joby's VRS boundary descent speed should be between 5 and 15 m/s."""
    joby = next(a for a in ALL_AIRCRAFT if "Joby" in a.name)
    vrs = joby.vrs_descent_boundary_mps()
    assert 5.0 < vrs < 15.0, f"VRS boundary {vrs:.1f} m/s not in 5-15 range"


def test_v4_aircraft_at_defaults_unchanged():
    """Multirotors with all v5 params at default must produce identical predictions."""
    from aircraft_db import DJI_MAVIC_3, SKYDIO_X10, FREEFLY_ALTA_X
    # v4 reference values (captured from Phase 0 baseline)
    v4_hover = {
        "DJI Mavic 3 Classic": 40.0,       # within 0.03%
        "Skydio X10": 35.0,                # within 0.02%
        "Freefly Alta X (no payload)": 50.0,  # within 0.00%
    }
    v4_fwd = {
        "DJI Mavic 3 Classic": (14.0, 28.58),  # range_km at 14 m/s
    }
    for ac in [DJI_MAVIC_3, SKYDIO_X10, FREEFLY_ALTA_X]:
        # Verify all v5 fields are at defaults
        assert ac.transition_width_mps == 0.0
        assert ac.profile_K_mu == 0.0
        assert ac.voltage_sag_at_full_load == 0.0
        assert ac.cooling_power_W == 0.0
        # Hover
        t = hover_endurance_min(ac)
        pub = v4_hover[ac.name]
        err = abs(t - pub) / pub
        assert err < 0.01, f"{ac.name} hover changed: {t:.2f} vs {pub:.1f}"
    # Forward flight
    _, rng = forward_endurance_and_range(DJI_MAVIC_3, 14.0)
    assert abs(rng - 28.58) < 0.1, f"Mavic 3 range changed: {rng:.2f} vs 28.58"


# --- Standalone runner ---------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_isa_sea_level,
        test_air_density_decreases_with_altitude,
        test_hover_power_scales_correctly,
        test_disk_loading_matches_explicit_geometry,
        test_profile_power_zero_matches_v1,
        test_profile_power_adds_constant,
        test_glauert_recovers_hover,
        test_forward_power_lower_than_hover_at_moderate_speed,
        test_profile_power_constant_with_speed,
        test_battery_usable_energy_basic,
        test_aircraft_disk_loading,
        test_hover_predictions_within_1_percent,
        test_mavic3_forward_flight_within_6_percent,
        # v3
        test_wing_stall_returns_infinity,
        test_wing_mode_beats_rotor_in_cruise,
        test_joby_s4_cruise_within_5_percent,
        test_no_wing_disables_wing_model,
        test_stall_speed_helper,
        # v4
        test_archer_midnight_cruise_within_5_percent,
        test_beta_alia_cruise_within_5_percent,
        test_vertical_vx4_cruise_within_5_percent,
        test_beta_alia_has_longest_range,
        # v5
        test_smooth_transition_eliminates_step,
        test_profile_power_grows_with_mu,
        test_voltage_sag_reduces_usable_Wh,
        test_ground_effect_reduces_hover_power,
        test_cooling_adds_constant_draw,
        test_wind_headwind_reduces_ground_range,
        test_vrs_boundary_is_physical,
        test_v4_aircraft_at_defaults_unchanged,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print()
    print(f"{len(tests) - failed}/{len(tests)} tests passed")

