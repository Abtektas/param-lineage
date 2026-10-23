"""What the page does with the parameters PX4 v1.18.0-rc1 removed or retyped.

The facts (kind, commit, note, successors) are in data/curated/v1.17.0..v1.18.0-rc1.json. This
file holds only the page's behaviour, keyed by parameter name:

  conversion rules  for the "migrated" entries: repeat what param_translation.cpp of the target
                    does on an in-place upgrade, so the corrected file gets the same values. The
                    page tests check every rule against data/translations/v1.18.0-rc1.json.
  suggestions       for other entries: a value the user can set by hand. The page never writes
                    it to the corrected file, because PX4 does not convert it.
"""

RULES = {
    "COM_RC_OVERRIDE": {"type": "if_zero_set", "to": "MAN_OVERRIDE_SPD", "value": -1.0},
    "EKF2_GPS_DELAY": {"type": "copy_int", "to": ["SENS_GPS0_DELAY", "SENS_GPS1_DELAY"]},
    **{f"EKF2_GPS_POS_{a}": {"type": "rename", "to": f"SENS_GPS0_OFF{a}"} for a in ("X", "Y", "Z")},
    "MNT_RANGE_PITCH": {"type": "half_range", "max": "MNT_MAX_PITCH", "min": "MNT_MIN_PITCH"},
    "MOT_POLE_COUNT": {"type": "copy", "to": [f"DSHOT_MOT_POL{i}" for i in range(1, 13)]},
    "MPC_LAND_RC_HELP": {"type": "if_nonzero_set_bit", "to": "MPC_AUTO_NUDGING", "bit": 1},

    "DSHOT_BIDIR_EN": {"type": "bdshot_hint"},
    **{f"EKF2_AGP_{s}": {"type": "suggest_rename", "to": f"EKF2_AGP0_{s}"}
       for s in ("CTRL", "MODE", "DELAY", "NOISE", "GATE")},
    "FD_ACT_MOT_TOUT": {"type": "suggest_scale", "to": "MOTFAIL_TIME", "factor": 0.001},
    **{old: {"type": "suggest_rename", "to": new}
       for old, new in (("SENS_IMU_TEMP", "HEATER1_TEMP"), ("SENS_IMU_TEMP_FF", "HEATER1_TEMP_FF"),
                        ("SENS_IMU_TEMP_I", "HEATER1_TEMP_I"), ("SENS_IMU_TEMP_P", "HEATER1_TEMP_P"),
                        ("SENS_TEMP_ID", "HEATER1_SENS_ID"))},
}

# The rule types that write to the corrected file. Only "migrated" entries may have them.
CONVERSIONS = {"rename", "copy", "copy_int", "half_range", "if_zero_set", "if_nonzero_set_bit"}

# Parameters whose type changed (data/changes), with the conversion the target's
# param_translation.cpp applies and how QGroundControl loads the old value.
TYPE_RULES = {
    **{f"RC{i}_REV": {"type": "sign", "commit": "139279747e", "pr": 26833,
                      "note": "Changed from float to int32. QGroundControl cannot read the saved \"-1.000000\" into the integer parameter and sends 0 instead, which PX4 treats as not reversed. Use the corrected file, which writes -1 or 1."}
       for i in range(1, 19)},
}
