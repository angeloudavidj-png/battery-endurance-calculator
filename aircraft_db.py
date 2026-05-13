"""
aircraft_db.py
==============
Reference aircraft used for model validation.

For each aircraft we record:
    - figure_of_merit (FoM_induced): induced-power efficiency, ~ 1 / kappa.
                     Textbook kappa is 1.15 -> FoM_induced ~ 0.87. Premium
                     rotor designs reach 0.90.
    - profile_power_W: rotor profile drag converted to hover-equivalent power.
                     Tuned per aircraft to match published hover endurance.
                     Stays constant with forward speed (v2 upgrade).
    - drivetrain_efficiency: motor + ESC; consumer ~ 0.72, premium ~ 0.82-0.92.

For eVTOLs with a wing, we also record wing geometry (S, b, Cd0, e, CL_max,
prop_eff). Cd0 is back-solved to match the manufacturer's published range
claim at a typical cruise speed -- so the *model* matches the *spec*, with
the resulting Cd0 lumping in any real-world overhead (climb/descent energy,
feathered-rotor drag for lift+cruise designs, etc.).

Three eVTOL architectures are now represented:
    - Tilt-rotor:    Joby S4         (all 6 rotors tilt, function as both)
    - Tilt+lift:     Vertical VX4    (4 tilt + 4 fixed lift)
    - Lift+cruise:   Archer Midnight (6 tilt + 6 fixed lift)
    - Lift+pusher:   Beta ALIA-250   (4 lift + 1 rear pusher)

Sources (verified May 2026):
    - DJI Mavic 3:     dji.com/mavic-3-classic/specs
    - Skydio X10:      skydio.com/x10/faqs; X10D datasheet PDF
    - Freefly Alta X:  freeflysystems.com/alta-x; advexure.com
    - Joby S4:         FAA airworthiness criteria for JAS4-1 (MTOW 4,800 lb);
                       Stoll, A. (NASA, 2015) for shaft-power anchor;
                       aopa.org for cruise / range claims.
    - Archer Midnight: archer.com investor relations; aviationevangelist.com;
                       newatlas.com (100 mi, 150 mph, 12-tilt-6 architecture);
                       Honeywell partner blog for 12-tilt-6 propulsion detail.
    - Beta ALIA-250:   airport-technology.com (50 ft span, 6,000 lb MTOW,
                       463 km range, 270 km/h max cruise); militaryfactory.com;
                       evtol.news for architecture (4 lift + 1 pusher).
    - Vertical VX4:    Vertical Aerospace press releases (8 prop, 4 tilt
                       + 4 fixed lift, 150 mph, 100 mi); leehamnews.com
                       analysis (battery 144 kWh, mass ~2,500 kg estimated;
                       Vertical does not officially publish MTOW).
"""

from endurance import Aircraft


# --- Multirotor reference aircraft ----------------------------------------

DJI_MAVIC_3 = Aircraft(
    name="DJI Mavic 3 Classic",
    mass_kg=0.895,
    n_rotors=4,
    rotor_diameter_m=0.239,             # 9.4 in
    battery_capacity_Ah=5.000,
    battery_voltage_V=15.4,             # 4S LiPo nominal
    Cd_body=1.10,
    frontal_area_m2=0.020,
    figure_of_merit=0.87,               # kappa = 1.15 (textbook)
    drivetrain_efficiency=0.72,
    profile_power_W=26.8,               # tuned to 40-min hover spec
    usable_fraction=0.90,
    discharge_efficiency=0.96,
    notes=("Published: 40 min hover, 46 min flight @ 9 m/s, 30 km range @ 14 m/s. "
           "Profile = 37 % of shaft hover power; low-Reynolds-number 9.4 in props."),
)

SKYDIO_X10 = Aircraft(
    name="Skydio X10",
    mass_kg=2.11,
    n_rotors=4,
    rotor_diameter_m=0.254,             # ~10 in, ESTIMATED -- see note
    battery_capacity_Ah=8.419,
    battery_voltage_V=18.55,            # 5S Li-ion nominal
    Cd_body=1.05,
    frontal_area_m2=0.045,
    figure_of_merit=0.90,               # premium 3-blade design
    drivetrain_efficiency=0.82,
    profile_power_W=41.3,               # tuned to 35-min hover spec
    usable_fraction=0.90,
    discharge_efficiency=0.96,
    notes=("Published: 35 min hover, 40 min max flight. "
           "Skydio does NOT publish rotor diameter; 10 in estimated from "
           "the 79.0 x 65.0 cm unfolded footprint. Profile is just 22 % of "
           "shaft hover power -- consistent with Skydio's quiet-prop priority."),
)

FREEFLY_ALTA_X = Aircraft(
    name="Freefly Alta X (no payload)",
    mass_kg=14.0,                       # ~10.4 kg airframe + 2 x ~1.8 kg packs
    n_rotors=4,
    rotor_diameter_m=0.838,             # 33 in ActiveBlade
    battery_capacity_Ah=32.0,           # 2 x 16 Ah in parallel
    battery_voltage_V=44.4,             # 12S LiPo nominal
    Cd_body=1.20,
    frontal_area_m2=0.18,
    figure_of_merit=0.87,
    drivetrain_efficiency=0.78,
    profile_power_W=353.7,              # tuned to 50-min hover spec
    usable_fraction=0.90,
    discharge_efficiency=0.96,
    notes=("Published: 50 min hover (no payload), 41.7 min at 5 lb payload. "
           "Flying weight estimated as airframe (~23 lb) + 2 batteries (~8 lb)."),
)


# --- eVTOL extension ------------------------------------------------------

JOBY_S4 = Aircraft(
    name="Joby S4 (eVTOL, MTOW)",
    mass_kg=2177.0,                     # 4,800 lb FAA MTOW for JAS4-1
    n_rotors=6,                         # six tilt-rotors (4 wing + 2 V-tail)
    rotor_diameter_m=2.9,               # ~9.5 ft (Stoll 2015 NASA paper)
    battery_capacity_Ah=1650.0,         # 165 kWh / 100 V nominal pack-equiv.
    battery_voltage_V=100.0,            # nominal pack voltage (Joby doesn't publish)
    Cd_body=0.30,                       # streamlined fixed-wing-style fuselage
    frontal_area_m2=2.4,                # ~estimated, 4-seat cabin frontal
    figure_of_merit=0.85,               # large-rotor induced inflow
    drivetrain_efficiency=0.92,         # premium PMSM motors + SiC inverters
    profile_power_W=134_100.0,          # tuned to Stoll 2015 (560 hp @ 1815 kg)
    usable_fraction=0.85,               # eVTOL: FAA Part 135 reserves
    discharge_efficiency=0.96,
    # v3 wing parameters
    wing_area_m2=20.2,                  # estimated from 39 ft span / AR ~7
    wing_span_m=11.9,                   # 39 ft (AOPA spec)
    Cd0=0.0291,                         # tuned to 161 km range @ 74 m/s
    oswald_e=0.80,                      # clean wing assumption
    CL_max=1.3,                         # clean wing, no flaps
    prop_efficiency=0.85,               # cruise-pitched propeller
    notes=("MTOW 4,800 lb per FAA special-class airworthiness criteria for JAS4-1. "
           "Six tilt-rotors with 5-blade props of ~2.9 m diameter (technical "
           "reference, not officially confirmed by Joby). Profile power calibrated "
           "to Stoll (NASA 2015) shaft-power estimate of 560 hp at 1815 kg. "
           "Wing area estimated from 39 ft span at AR ~7; Cd0 tuned to match "
           "Joby's 100 mi (161 km) range claim at 74 m/s (165 mph, ~144 kt) "
           "mid-cruise. Joby's max cruise per AOPA + NASA acoustic paper is "
           "170-175 kt (87-90 m/s); this validation point sits below max "
           "cruise as a representative economy-cruise speed. "
           "v3 model: wing-borne cruise above V_stall = 36 m/s; rotor-borne "
           "below. Disk loading 539 N/m^2 is ~ 10x typical multirotor."),
)


ARCHER_MIDNIGHT = Aircraft(
    name="Archer Midnight (eVTOL, MTOW)",
    mass_kg=2948.0,                     # 6,500 lb (Robb Report, aviationevangelist)
    n_rotors=12,                        # 12-tilt-6: 6 tilt (5-blade) + 6 fixed lift (2-blade)
    rotor_diameter_m=2.5,               # ESTIMATED; Archer doesn't publish
    battery_capacity_Ah=1400.0,         # 140 kWh / 100 V nominal; 6 packs (Honeywell blog)
    battery_voltage_V=100.0,
    Cd_body=0.32,                       # fuselage + V-tail
    frontal_area_m2=2.5,                # 5-seat cabin
    figure_of_merit=0.85,
    drivetrain_efficiency=0.92,
    profile_power_W=150_000.0,          # ESTIMATED for 12 rotors (mix of 5 and 2 blade)
    usable_fraction=0.85,
    discharge_efficiency=0.96,
    wing_area_m2=18.0,                  # estimated from 40 ft span at AR ~8
    wing_span_m=12.2,                   # 40 ft (AOPA Maker; Midnight may be larger)
    Cd0=0.0238,                         # back-solved for 161 km @ 67 m/s
    oswald_e=0.80,
    CL_max=1.3,
    prop_efficiency=0.85,
    notes=("MTOW 6,500 lb per Archer + aviation press. 12-tilt-6 architecture: "
           "6 wing-leading-edge tilt-rotors (5-blade) provide both lift and "
           "cruise thrust; 6 trailing-edge fixed lift props (2-blade) feather "
           "in cruise. Battery 140 kWh from 6 packs. Range 100 mi (161 km) at "
           "67 m/s (150 mph) cruise; the model's Cd0 lumps in parasite drag "
           "from feathered lift rotors. Wingspan 40 ft per Maker; production "
           "Midnight may be slightly larger (~48 ft per some sources)."),
)


BETA_ALIA_250 = Aircraft(
    name="Beta ALIA-250 (eVTOL, MTOW)",
    mass_kg=2721.0,                     # 6,000 lb (Beta + airport-technology)
    n_rotors=4,                         # 4 horizontal lift rotors; pusher separate
    rotor_diameter_m=3.5,               # ESTIMATED; Beta doesn't publish
    battery_capacity_Ah=3500.0,         # ~350 kWh / 100 V; long-range mission profile
    battery_voltage_V=100.0,            # actual pack reaches 950 V DC, normalized here
    Cd_body=0.28,                       # clean lift+pusher with V-tail
    frontal_area_m2=2.5,
    figure_of_merit=0.87,               # dedicated lift rotors, optimized for hover
    drivetrain_efficiency=0.92,
    profile_power_W=80_000.0,           # just 4 lift rotors; small profile budget
    usable_fraction=0.85,
    discharge_efficiency=0.96,
    wing_area_m2=19.4,                  # 15.24 m span at AR ~12 (Arctic-tern-inspired)
    wing_span_m=15.24,                  # 50 ft (Beta spec, airport-technology)
    Cd0=0.0287,                         # back-solved for 463 km @ 62 m/s
    oswald_e=0.85,                      # high-AR wing, well-shaped
    CL_max=1.4,                         # high-AR wing tolerates higher CL
    prop_efficiency=0.88,               # dedicated rear pusher prop
    notes=("MTOW 6,000 lb per Beta + airport-technology. Architecture: 4 "
           "horizontal lift rotors + 1 rear pusher prop. In cruise the 4 "
           "lift rotors feather/stop and only the pusher works. Wing "
           "configuration inspired by the Arctic tern -- 50 ft span, "
           "high aspect ratio (~12) for long-range efficiency. Range "
           "463 km (250 nm) is the longest of the eVTOL class. Battery "
           "capacity 350 kWh estimated; Beta uses 950 V DC pack with "
           "350 kW rapid charge in <60 min. Cd0 back-solved at 62 m/s "
           "(138 mph) standard cruise; max cruise is 75 m/s (270 km/h)."),
)


VERTICAL_VX4 = Aircraft(
    name="Vertical VX4 (eVTOL, est MTOW)",
    mass_kg=2500.0,                     # ESTIMATED; Vertical does not officially publish
    n_rotors=8,                         # 4 front tilt + 4 rear fixed lift
    rotor_diameter_m=2.2,               # ESTIMATED; not officially published
    battery_capacity_Ah=1440.0,         # 144 kWh / 100 V (Leeham News analysis)
    battery_voltage_V=100.0,
    Cd_body=0.30,
    frontal_area_m2=2.4,
    figure_of_merit=0.85,
    drivetrain_efficiency=0.92,
    profile_power_W=110_000.0,          # ESTIMATED for 8 smaller rotors
    usable_fraction=0.85,
    discharge_efficiency=0.96,
    wing_area_m2=17.0,                  # estimated from ~12 m span at AR ~8.5
    wing_span_m=12.0,                   # ESTIMATED; not officially published
    Cd0=0.0309,                         # back-solved for 161 km @ 67 m/s
    oswald_e=0.80,
    CL_max=1.3,
    prop_efficiency=0.85,
    notes=("Mass 2,500 kg ESTIMATED; Vertical Aerospace does NOT officially "
           "publish MTOW. Estimate is consistent with Leeham News engineering "
           "analysis (October 2022) which derived ~2,500 kg total to fit a "
           "144 kWh battery system. Architecture: 8 wing-mounted props -- "
           "4 front tilt-rotors and 4 rear fixed-lift rotors that operate "
           "only during takeoff and landing. Battery 144 kWh proprietary "
           "(manufactured at Vertical Energy Centre, Bristol). 2024 prototype "
           "has 20% power-to-weight increase over earlier version. Range "
           "100 mi (161 km) at 150 mph (67 m/s) certification target. "
           "Rotor diameter 2.2 m and wing geometry are estimates."),
)


ALL_AIRCRAFT = [
    DJI_MAVIC_3,
    SKYDIO_X10,
    FREEFLY_ALTA_X,
    JOBY_S4,
    ARCHER_MIDNIGHT,
    BETA_ALIA_250,
    VERTICAL_VX4,
]


# --- Published / derived reference data ----------------------------------

PUBLISHED_HOVER_MIN = {
    "DJI Mavic 3 Classic":              40.0,   # DJI spec
    "Skydio X10":                       35.0,   # Skydio spec
    "Freefly Alta X (no payload)":      50.0,   # Freefly spec
    "Joby S4 (eVTOL, MTOW)":            14.7,   # DERIVED: Stoll 560 hp shaft @ 1815 kg
                                                #          scaled to MTOW; 165 kWh battery,
                                                #          85 % usable, 92 % drivetrain.
                                                #          Not a Joby-published spec.
    "Archer Midnight (eVTOL, MTOW)":    10.0,   # DERIVED from 140 kWh battery + model
    "Beta ALIA-250 (eVTOL, MTOW)":      26.5,   # DERIVED from 350 kWh battery + model
    "Vertical VX4 (eVTOL, est MTOW)":   10.2,   # DERIVED from 144 kWh battery + model
}

PUBLISHED_HOVER_NOTE = {
    "Joby S4 (eVTOL, MTOW)":
        "Derived: shaft-power scaled from Stoll 2015 to MTOW, with public "
        "battery and assumed drivetrain efficiency. Joby does not publish "
        "hover endurance directly.",
    "Archer Midnight (eVTOL, MTOW)":
        "Derived: hover power computed from rotor disk theory using 12-rotor "
        "estimated geometry; 140 kWh battery. Archer does not publish "
        "hover endurance directly.",
    "Beta ALIA-250 (eVTOL, MTOW)":
        "Derived: hover power computed from 4 lift-rotor estimated geometry; "
        "350 kWh battery estimate. Long hover endurance reflects Beta's "
        "range-optimized design (large battery, dedicated lift rotors). "
        "Beta does not publish hover endurance directly.",
    "Vertical VX4 (eVTOL, est MTOW)":
        "Derived: hover power computed using estimated 8-rotor geometry "
        "(Vertical does not publish rotor diameter or wing area) and "
        "Leeham News estimate of 144 kWh battery / ~2,500 kg mass. "
        "Vertical does not publish hover endurance directly.",
}


# Forward-flight reference points: (airspeed_mps, value, kind)
# kind = 'range_km' or 'endurance_min'
PUBLISHED_FORWARD_REFS = {
    "DJI Mavic 3 Classic": [
        (14.0, 30.0, "range_km"),         # 30 km max range at 50.4 km/h
        ( 9.0, 46.0, "endurance_min"),    # 46 min flight time at 32.4 km/h
    ],
    "Joby S4 (eVTOL, MTOW)": [
        # Joby's 100 mi range, validated at 74 m/s (165 mph, 144 kt). This
        # is below Joby's max cruise of 170-175 kt (87-90 m/s) and serves as
        # a representative mid/economy cruise speed.
        (74.0, 161.0, "range_km"),
    ],
    "Archer Midnight (eVTOL, MTOW)": [
        # Archer's published max range of 100 mi at 150 mph (67 m/s) cruise.
        # In cruise, the 6 lift-only props feather; only 6 tilt props provide
        # thrust. The model's Cd0 = 0.0238 lumps in feathered-prop parasite drag.
        (67.0, 161.0, "range_km"),
    ],
    "Beta ALIA-250 (eVTOL, MTOW)": [
        # Beta's 250 nm (463 km) range claim at 138 mph (62 m/s) standard
        # cruise. Max cruise is 75 m/s. In cruise the 4 lift rotors feather
        # and the rear pusher provides all thrust.
        (62.0, 463.0, "range_km"),
    ],
    "Vertical VX4 (eVTOL, est MTOW)": [
        # Vertical's 100 mi (161 km) range claim at 150 mph (67 m/s)
        # certification cruise speed. In cruise the 4 rear fixed-lift props
        # feather; only the 4 front tilt props provide thrust.
        (67.0, 161.0, "range_km"),
    ],
}
