"""
validate.py
===========
Run the calculator against published commercial UAS specs.

Two validation tracks:
    1. HOVER  -- compare predicted hover endurance to published spec for
                 each reference aircraft (Mavic 3, X10, Alta X).
    2. FWD    -- compare predicted forward-flight performance at the
                 manufacturer's published test condition (currently only
                 the Mavic 3 publishes a usable airspeed-tied datapoint).

Three commands:
    python validate.py                 # full hover + forward-flight table
    python validate.py --csv           # also write validation_results.csv
    python validate.py --quick ...     # plug in a one-off aircraft (see --help)
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import replace

from aircraft_db import ALL_AIRCRAFT, PUBLISHED_HOVER_MIN, PUBLISHED_FORWARD_REFS
from endurance import (
    Aircraft,
    G,
    air_density,
    hover_power_momentum_theory,
    hover_endurance_min,
    forward_flight_power,
    forward_endurance_and_range,
    best_cruise_speed,
)


# Universal defaults: what someone would use without per-aircraft tuning.
UNTUNED_FOM = 0.65
UNTUNED_ETA = 0.78


# --------------------------------------------------------------------- helpers

def predict_hover_min(ac: Aircraft, fom: float, eta: float) -> float:
    """Re-evaluate hover endurance with overridden FoM/eta and profile_power=0.

    Used to produce the 'untuned' baseline (what someone would get without
    per-aircraft calibration: lumped-FoM model, no profile drag term).
    """
    overridden = replace(ac, figure_of_merit=fom, drivetrain_efficiency=eta,
                         profile_power_W=0.0)
    return hover_endurance_min(overridden)


def pct_err(predicted: float, published: float) -> float:
    return 100.0 * (predicted - published) / published


# --------------------------------------------------------------------- hover

def run_hover_validation(verbose: bool = True) -> list[dict]:
    rows: list[dict] = []
    for ac in ALL_AIRCRAFT:
        published = PUBLISHED_HOVER_MIN[ac.name]
        t_untuned = predict_hover_min(ac, UNTUNED_FOM, UNTUNED_ETA)
        t_tuned = hover_endurance_min(ac)
        P_hover = hover_power_momentum_theory(
            ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
            ac.figure_of_merit, ac.drivetrain_efficiency,
        )
        rows.append({
            "aircraft":             ac.name,
            "mass_kg":              ac.mass_kg,
            "rotor_dia_m":          ac.rotor_diameter_m,
            "battery_Wh_nameplate": round(ac.nameplate_Wh, 1),
            "disk_loading_Nm2":     round(ac.disk_loading_Nm2, 1),
            "P_hover_W_tuned":      round(P_hover, 1),
            "tuned_FoM":            ac.figure_of_merit,
            "tuned_eta_drive":      ac.drivetrain_efficiency,
            "published_hover_min":  published,
            "predicted_untuned":    round(t_untuned, 1),
            "err_untuned_pct":      round(pct_err(t_untuned, published), 1),
            "predicted_tuned":      round(t_tuned, 1),
            "err_tuned_pct":        round(pct_err(t_tuned, published), 2),
        })

    if verbose:
        print()
        print("=" * 92)
        print("HOVER VALIDATION -- Predicted vs Published Hover Endurance")
        print("=" * 92)
        hdr = (f"{'Aircraft':<28}{'Mass':>7}{'Wh':>8}{'DL':>7}{'Pub':>7}"
               f"{'Untuned':>9}{'Err%':>7}{'Tuned':>8}{'Err%':>7}")
        print(hdr)
        print("-" * 92)
        for r in rows:
            print(f"{r['aircraft']:<28}"
                  f"{r['mass_kg']:>7.2f}"
                  f"{r['battery_Wh_nameplate']:>8.0f}"
                  f"{r['disk_loading_Nm2']:>7.0f}"
                  f"{r['published_hover_min']:>7.0f}"
                  f"{r['predicted_untuned']:>9.1f}"
                  f"{r['err_untuned_pct']:>+7.1f}"
                  f"{r['predicted_tuned']:>8.1f}"
                  f"{r['err_tuned_pct']:>+7.2f}")
        print("-" * 92)
        max_u = max(abs(r["err_untuned_pct"]) for r in rows)
        max_t = max(abs(r["err_tuned_pct"])   for r in rows)
        print(f"Max |error|  universal defaults : {max_u:5.1f} %")
        print(f"Max |error|  per-aircraft tune  : {max_t:5.2f} %")
        print()
    return rows


# Alias for app.py compatibility
run_validation = run_hover_validation


# --------------------------------------------------------------------- forward

def run_forward_validation(verbose: bool = True) -> list[dict]:
    """Validate forward-flight against published manufacturer numbers.

    For each (aircraft, test airspeed, published metric) triple, we report
    the model prediction and error. We also report the model's own best-range
    cruise speed -- this is the apples-to-apples 'max range' comparison.
    """
    rows: list[dict] = []
    for ac in ALL_AIRCRAFT:
        refs = PUBLISHED_FORWARD_REFS.get(ac.name, [])
        if not refs:
            continue
        # Wing-borne aircraft cruise at much higher V than multirotors,
        # so widen the search range to capture their best-range point.
        v_max_search = 110.0 if ac.has_wing else 25.0
        V_best, range_best, t_best = best_cruise_speed(
            ac, v_min=1.0, v_max=v_max_search, n_pts=221,
        )
        for V_test, target, kind in refs:
            t_min, rng_km = forward_endurance_and_range(ac, V_test)
            if kind == "range_km":
                predicted = rng_km
                metric = f"range@{V_test:g} m/s"
                units = "km"
            elif kind == "endurance_min":
                predicted = t_min
                metric = f"endurance@{V_test:g} m/s"
                units = "min"
            else:
                continue
            rows.append({
                "aircraft":           ac.name,
                "metric":             metric,
                "units":              units,
                "published":          target,
                "predicted":          round(predicted, 2),
                "err_pct":            round(pct_err(predicted, target), 1),
                "V_best_mps":         round(V_best, 1),
                "range_best_km":      round(range_best, 2),
                "endurance_best_min": round(t_best, 1),
            })

    if verbose and rows:
        print()
        print("=" * 92)
        print("FORWARD-FLIGHT VALIDATION -- Predicted vs Published Cruise Performance")
        print("=" * 92)
        hdr = (f"{'Aircraft':<28}{'Metric':<22}{'Pub':>8}"
               f"{'Pred':>9}{'Err%':>8}{'V_best':>9}{'R_best':>9}")
        print(hdr)
        print("-" * 92)
        for r in rows:
            pub  = f"{r['published']:.1f} {r['units']}"
            pred = f"{r['predicted']:.2f}"
            vb   = f"{r['V_best_mps']:.1f}"
            rb   = f"{r['range_best_km']:.2f}"
            print(f"{r['aircraft']:<28}{r['metric']:<22}{pub:>8}"
                  f"{pred:>9}{r['err_pct']:>+7.1f}%{vb:>9}{rb:>9}")
        print("-" * 92)
        print("V_best   = model's best-range cruise speed [m/s]")
        print("R_best   = predicted range at V_best [km] (apples-to-apples vs max-range claim)")
        print()

        # Apples-to-apples max-range comparison (Mavic 3 only currently)
        for ac in ALL_AIRCRAFT:
            if ac.name == "DJI Mavic 3 Classic":
                V_best, range_best, _ = best_cruise_speed(ac, v_min=1.0, v_max=25.0)
                pub_max = 30.0
                err_apples = pct_err(range_best, pub_max)
                print(f"Apples-to-apples max-range check (Mavic 3):")
                print(f"  Published max range            : {pub_max:.1f} km (DJI tested @ 14.0 m/s)")
                print(f"  Predicted max range  (V={V_best:.1f})  : {range_best:.2f} km")
                print(f"  Error                          : {err_apples:+.1f} %")
                print()
        print("v5 NOTE: v4 physics preserved at defaults; seven opt-in extensions:")
        print("smooth sigmoid transition, profile-power mu-scaling, battery voltage")
        print("sag, Cheeseman-Bennett ground effect, cooling parasitic load, wind")
        print("headwind for ground range, and VRS descent boundary (informational).")
        print("eVTOLs opt in to transition, mu-scaling, and cooling; Cd0 re-tuned.")
        print("Multirotors stay at v4 defaults -- predictions unchanged.")
        print()
    return rows


# --------------------------------------------------------------------- quick

def run_quick(args: argparse.Namespace) -> None:
    """Plug in a one-off aircraft from CLI flags."""
    rotor_dia_m = (args.prop_in / 39.3701) if args.prop_in else args.prop_m
    voltage_V = args.cells * args.v_per_cell

    ac = Aircraft(
        name=args.name,
        mass_kg=args.mass,
        n_rotors=args.rotors,
        rotor_diameter_m=rotor_dia_m,
        battery_capacity_Ah=args.cap_ah,
        battery_voltage_V=voltage_V,
        Cd_body=args.cd,
        frontal_area_m2=args.frontal_area,
        figure_of_merit=args.fom,
        drivetrain_efficiency=args.eta,
        profile_power_W=args.profile_power,
        usable_fraction=args.usable,
        discharge_efficiency=args.batt_eff,
    )

    print()
    print("=" * 60)
    print(f"QUICK ESTIMATE -- {ac.name}")
    print("=" * 60)
    print(f"  Mass               : {ac.mass_kg:.3f} kg")
    print(f"  Rotors             : {ac.n_rotors} x {ac.rotor_diameter_m*39.37:.2f} in "
          f"(disk area {ac.disk_area_m2:.4f} m^2)")
    print(f"  Disk loading       : {ac.disk_loading_Nm2:.1f} N/m^2")
    print(f"  Battery nameplate  : {ac.nameplate_Wh:.1f} Wh "
          f"({ac.battery_capacity_Ah:.2f} Ah x {ac.battery_voltage_V:.2f} V)")
    print(f"  FoM (induced)      : {ac.figure_of_merit:.3f}")
    print(f"  eta_drivetrain     : {ac.drivetrain_efficiency:.3f}")
    print(f"  Profile power      : {ac.profile_power_W:.1f} W (constant w/ V)")
    print()

    P_hover = hover_power_momentum_theory(
        ac.mass_kg, ac.n_rotors, ac.rotor_diameter_m,
        ac.figure_of_merit, ac.drivetrain_efficiency,
        altitude_m=args.altitude, temperature_offset_c=args.dT,
    )
    t_hover = hover_endurance_min(ac, args.altitude, args.dT)
    V_best, range_best, t_best = best_cruise_speed(
        ac, args.altitude, args.dT, v_min=1.0, v_max=30.0,
    )

    rho = air_density(args.altitude, args.dT)
    print(f"  Atmosphere         : rho = {rho:.4f} kg/m^3 "
          f"(altitude {args.altitude} m, dT {args.dT:+d} C)")
    print()
    print(f"  Hover power        : {P_hover:6.1f} W")
    print(f"  Hover endurance    : {t_hover:6.1f} min")
    print(f"  Best cruise speed  : {V_best:6.1f} m/s ({V_best*3.6:.1f} km/h)")
    print(f"  Endurance @ V_best : {t_best:6.1f} min")
    print(f"  Range     @ V_best : {range_best:6.2f} km")
    print()

    if args.at_speed is not None:
        V = args.at_speed
        P = forward_flight_power(
            ac.mass_kg, V, ac.n_rotors, ac.rotor_diameter_m,
            ac.Cd_body, ac.frontal_area_m2,
            ac.figure_of_merit, ac.drivetrain_efficiency,
            altitude_m=args.altitude, temperature_offset_c=args.dT,
        )
        t_min, rng_km = forward_endurance_and_range(ac, V, args.altitude, args.dT)
        print(f"  @ user speed {V:.1f} m/s:")
        print(f"    Power           : {P:.1f} W")
        print(f"    Endurance       : {t_min:.1f} min")
        print(f"    Range           : {rng_km:.2f} km")
        print()


# --------------------------------------------------------------------- csv

def write_csv(hover_rows: list[dict], fwd_rows: list[dict],
              path: str = "validation_results.csv") -> None:
    if not hover_rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(hover_rows[0].keys()))
        w.writeheader()
        w.writerows(hover_rows)
    print(f"Wrote {path}")
    if fwd_rows:
        fwd_path = path.replace(".csv", "_forward.csv")
        with open(fwd_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fwd_rows[0].keys()))
            w.writeheader()
            w.writerows(fwd_rows)
        print(f"Wrote {fwd_path}")


# --------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--csv", action="store_true",
                   help="write validation_results.csv and *_forward.csv")
    p.add_argument("--no-forward", action="store_true",
                   help="skip the forward-flight validation table")

    q = p.add_argument_group(
        "quick (--quick): one-off aircraft from the command line",
        ("Example: python validate.py --quick --mass 1.5 --rotors 4 "
         "--prop-in 10 --cap-ah 5.0 --cells 4 --at-speed 12")
    )
    q.add_argument("--quick", action="store_true",
                   help="run a one-off estimate instead of the standard validation")
    q.add_argument("--name", default="Custom multirotor")
    q.add_argument("--mass", type=float, default=1.5, help="mass [kg]")
    q.add_argument("--rotors", type=int, default=4, help="number of rotors")
    q.add_argument("--prop-in", type=float, default=None,
                   help="rotor diameter [in] (overrides --prop-m)")
    q.add_argument("--prop-m", type=float, default=0.254, help="rotor diameter [m]")
    q.add_argument("--cap-ah", type=float, default=5.0, help="battery capacity [Ah]")
    q.add_argument("--cells", type=int, default=4, help="series cells (S count)")
    q.add_argument("--v-per-cell", type=float, default=3.7,
                   help="nominal V per cell (3.7 Li-ion, 3.85 LiPo)")
    q.add_argument("--fom", type=float, default=0.65, help="rotor figure of merit (or induced-FoM if profile-power > 0)")
    q.add_argument("--eta", type=float, default=0.78, help="drivetrain efficiency")
    q.add_argument("--profile-power", type=float, default=0.0,
                   help="rotor profile power at hover [W] (v2 model; ~25-40 %% of shaft hover power)")
    q.add_argument("--usable", type=float, default=0.90, help="usable battery fraction")
    q.add_argument("--batt-eff", type=float, default=0.96, help="discharge efficiency")
    q.add_argument("--cd", type=float, default=1.0, help="body drag coefficient")
    q.add_argument("--frontal-area", type=float, default=0.04, help="frontal area [m^2]")
    q.add_argument("--altitude", type=int, default=0, help="altitude [m]")
    q.add_argument("--dT", type=int, default=0, help="temp offset from ISA [C]")
    q.add_argument("--at-speed", type=float, default=None,
                   help="report power/endurance/range at this airspeed [m/s]")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.quick:
        run_quick(args)
    else:
        hrows = run_hover_validation(verbose=True)
        frows = [] if args.no_forward else run_forward_validation(verbose=True)
        if args.csv:
            write_csv(hrows, frows)
