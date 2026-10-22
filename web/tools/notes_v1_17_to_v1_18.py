"""What happened to each parameter removed between PX4 v1.17.0 and v1.18.0-rc1.

Every entry was checked against the commit that removed the parameter (git log -S over
v1.17.0..v1.18.0-rc1) and the v1.18.0-rc1 source. Kinds:

  migrated  PX4's param_translation.cpp in the target converts it, but only when the
            vehicle's stored parameters are upgraded in place. "rule" repeats that
            conversion so a .params file can be fixed the same way.
  replaced  Newer parameters do the job, but PX4 does not convert the value.
  fixed     The behaviour is now fixed in the code; "fixed" is the value it is fixed at,
            when it matches an old setting.
  removed   The feature or setting is gone.
"""

FIXED_OLD_DEFAULT = "Removed; the value is now fixed in the code at the old default ({old})."

NOTES = {
    # airspeed selector wind estimator, 86800b4fdf
    **{name: {"kind": "fixed", "commit": "86800b4fdf", "note": FIXED_OLD_DEFAULT}
       for name in ("ASPD_BETA_GATE", "ASPD_BETA_NOISE", "ASPD_SCALE_NSD", "ASPD_TAS_GATE")},

    "BAT1_I_CHANNEL": {"kind": "fixed", "commit": "9c2e8aff0f", "pr": 26590,
                       "note": "Removed; the battery current ADC channel always comes from the board configuration and can no longer be overridden."},
    "BAT2_I_CHANNEL": {"kind": "fixed", "commit": "9c2e8aff0f", "pr": 26590,
                       "note": "Removed; the battery current ADC channel always comes from the board configuration and can no longer be overridden."},
    "BAT_ADC_CHANNEL": {"kind": "removed", "commit": "1550c8d245",
                        "note": "Was already unused (deprecated) in v1.17; removed."},

    "COM_ARM_SDCARD": {"kind": "fixed", "fixed": 1, "commit": "a061b8665b", "pr": 27259,
                       "note": "Removed; a missing SD card now always gives a warning (the old value 1). \"Disabled\" (0) and \"Enforce SD card presence\" (2) are no longer available."},
    "COM_DISARM_MAN": {"kind": "fixed", "fixed": 1, "commit": "0c0be00046",
                       "note": "Removed; disarming in flight with a stick, switch or button in manual thrust modes on multicopters is now always allowed (the old value 1)."},
    "COM_FLT_PROFILE": {"kind": "removed", "commit": "576e336849", "pr": 26735,
                        "note": "Had no effect; removed."},
    "COM_HLDL_REG_T": {"kind": "fixed", "fixed": 0, "commit": "4e2f3e7600", "pr": 26809,
                       "note": "Removed; a regained high-latency link is used immediately (the old value 0)."},
    "COM_IMB_PROP_ACT": {"kind": "fixed", "fixed": 0, "commit": "ffef31fb06", "pr": 27260,
                         "note": "Removed; an imbalanced propeller now always gives a warning (the old value 0). To turn the check off (old -1), set FD_IMB_PROP_THR to 0. \"Return\" (1) and \"Land\" (2) are no longer available."},
    "COM_KILL_DISARM": {"kind": "fixed", "fixed": 5.0, "commit": "6b5147110b", "pr": 26736,
                        "note": "Removed; the vehicle disarms 5 s after the kill switch is engaged."},
    "COM_LKDOWN_TKO": {"kind": "fixed", "fixed": 3.0, "commit": "5638ac53c7", "pr": 27262,
                       "note": "Removed; the time window for detecting a failure after takeoff is fixed at 3 s."},
    "COM_MOT_TEST_EN": {"kind": "fixed", "fixed": 1, "commit": "09cb22f799",
                        "note": "Removed; actuator testing can no longer be disabled."},
    "COM_OBC_LOSS_T": {"kind": "fixed", "fixed": 5.0, "commit": "5e86be131c", "pr": 27261,
                       "note": "Removed; onboard computer link loss is declared after 5 s."},
    "COM_RC_ARM_HYST": {"kind": "fixed", "fixed": 1000, "commit": "c8286d4bba",
                        "note": "Removed; arming and disarming with sticks or a button take 1 s (1000 ms)."},
    "COM_RC_OVERRIDE": {"kind": "migrated", "commit": "b8c5f66af0", "pr": 27041,
                        "rule": {"type": "if_zero_set", "to": "MAN_OVERRIDE_SPD", "value": -1.0},
                        "note": "Replaced by MAN_OVERRIDE_SPD: stick speed in 1/s, a negative value disables it. Only \"disabled\" (0) is converted, to MAN_OVERRIDE_SPD = -1. Otherwise override now works by stick speed and applies in both auto and offboard modes, on multicopters and VTOLs in multicopter mode."},
    "COM_RC_STICK_OV": {"kind": "replaced", "commit": "b8c5f66af0", "pr": 27041, "see": ["MAN_OVERRIDE_SPD"],
                        "note": "Replaced by MAN_OVERRIDE_SPD, which uses stick speed (1/s) instead of stick deflection (%). There is no conversion; check MAN_OVERRIDE_SPD (default 1.0)."},
    "COM_TAKEOFF_ACT": {"kind": "fixed", "fixed": 0, "commit": "eb06c7b7a9", "pr": 26808,
                        "note": "Removed; after takeoff the vehicle always switches to Hold (the old value 0). \"Mission (if valid)\" (1) is no longer available."},

    "DSHOT_BIDIR_EN": {"kind": "replaced", "commit": "f00e46f618", "rule": {"type": "bdshot_hint"},
                       "note": "Bidirectional DShot is now chosen per timer group in the output protocol parameters (PWM_MAIN_TIMn / PWM_AUX_TIMn, Actuators setup): BDShot150 (-8), BDShot300 (-7) or BDShot600 (-6). Not converted."},

    **{f"EKF2_AGP_{s}": {"kind": "replaced", "commit": "1d852907a2", "pr": 26306, "see": [f"EKF2_AGP0_{s}", "EKF2_AGP0_ID"],
                         "rule": {"type": "suggest_rename", "to": f"EKF2_AGP0_{s}"},
                         "note": f"Replaced by the per-source EKF2_AGPn_{s}. Not converted by v1.18.0-rc1 (a fix is proposed in PX4/PX4-Autopilot#29351). Put the value in EKF2_AGP0_{s}; the source is only used once EKF2_AGP0_ID matches the id field of its AuxGlobalPosition messages (0 disables it), and a changed ID needs a reboot."}
       for s in ("CTRL", "MODE", "DELAY", "NOISE", "GATE")},

    "EKF2_GPS_DELAY": {"kind": "migrated", "commit": "4b2e0a6f59", "pr": 26660,
                       "rule": {"type": "copy_int", "to": ["SENS_GPS0_DELAY", "SENS_GPS1_DELAY"]},
                       "note": "Replaced by the per-receiver SENS_GPS0_DELAY and SENS_GPS1_DELAY (integer ms)."},
    **{f"EKF2_GPS_POS_{a}": {"kind": "migrated", "commit": "89855926ef", "pr": 26634,
                             "rule": {"type": "rename", "to": f"SENS_GPS0_OFF{a}"},
                             "note": f"Replaced by the per-receiver SENS_GPS0_OFF{a}."}
       for a in ("X", "Y", "Z")},

    "FD_ACT_MOT_C2T": {"kind": "replaced", "commit": "6d0de7379b", "pr": 26990, "see": ["MOTFAIL_C2T", "MOTFAIL_OFF"],
                       "note": "Motor failure detection was reworked. The closest new parameter, MOTFAIL_C2T, is a scale used with the offset MOTFAIL_OFF and has a different default (35 instead of 2.0); do not copy the value."},
    "FD_ACT_MOT_THR": {"kind": "removed", "commit": "c5652b2084",
                       "note": "Removed with the motor failure detection rework; there is no replacement."},
    "FD_ACT_MOT_TOUT": {"kind": "replaced", "commit": "c5652b2084", "see": ["MOTFAIL_TIME"],
                        "rule": {"type": "suggest_scale", "to": "MOTFAIL_TIME", "factor": 0.001},
                        "note": "Replaced by MOTFAIL_TIME, in seconds instead of milliseconds, in the reworked motor failure detection (default 1 s instead of 100 ms). Not converted."},
    "FD_ESCS_EN": {"kind": "replaced", "commit": "c5652b2084", "see": ["FD_ACT_EN"],
                   "note": "The check of the ESCs' arming state now runs together with the motor failure check, both enabled by FD_ACT_EN, whose default changed from 1 to 0."},

    "FW_AT_START": {"kind": "removed", "commit": "ca83b8330d",
                    "note": "Was a trigger, not a setting. Autotune is now started with the autotune command from the ground station or with the AUX switch (FW_AT_MAN_AUX)."},
    "MC_AT_START": {"kind": "removed", "commit": "ca83b8330d",
                    "note": "Was a trigger, not a setting. Autotune is now started with the autotune command from the ground station."},
    **{name: {"kind": "fixed", "commit": "c4c68df4e4", "note": FIXED_OLD_DEFAULT}
       for name in ("FW_T_SPD_DEV_STD", "FW_T_SPD_PRC_STD", "FW_T_SPD_STD")},

    "GF_PREDICT": {"kind": "removed", "commit": "ece74e8d24", "pr": 27465,
                   "note": "The experimental pre-emptive geofence feature was removed."},
    "INA226_CONFIG": {"kind": "removed", "commit": "ad26499a36", "pr": 27364,
                      "note": "Removed; the rewritten INA226 driver always uses its built-in configuration."},
    "LNDMC_TRIG_TIME": {"kind": "fixed", "fixed": 1.0, "commit": "62f5f5267e", "pr": 25251,
                        "note": "Removed; the multicopter land detection time is fixed (1 s, the old default)."},

    **{f"MNT_OFF_{a}": {"kind": "removed", "commit": "0da6efa52d",
                        "note": "Removed; set the gimbal output offset with the trim of that output in the Actuators setup instead."}
       for a in ("PITCH", "ROLL", "YAW")},
    "MNT_RANGE_PITCH": {"kind": "migrated", "commit": "0fa5a83409",
                        "rule": {"type": "half_range", "max": "MNT_MAX_PITCH", "min": "MNT_MIN_PITCH"},
                        "note": "Replaced by MNT_MAX_PITCH and MNT_MIN_PITCH (half the range each way)."},
    "MOT_POLE_COUNT": {"kind": "migrated", "commit": "f00e46f618",
                       "rule": {"type": "copy", "to": [f"DSHOT_MOT_POL{i}" for i in range(1, 13)]},
                       "note": "Replaced by the per-motor DSHOT_MOT_POL1 to DSHOT_MOT_POL12."},
    "MPC_LAND_RC_HELP": {"kind": "migrated", "commit": "7ed3c5bad4", "pr": 27691,
                         "rule": {"type": "if_nonzero_set_bit", "to": "MPC_AUTO_NUDGING", "bit": 1},
                         "note": "Replaced by bit 1 (landing nudging) of MPC_AUTO_NUDGING."},
    "MPC_USE_HTE": {"kind": "fixed", "fixed": 1, "commit": "0d66981dcc", "pr": 24751,
                    "note": "Removed; the hover thrust estimate is always used for altitude control (the old value 1)."},

    **{old: {"kind": "replaced", "commit": "963a776fa6", "pr": 26325, "see": [new],
             "rule": {"type": "suggest_rename", "to": new},
             "note": f"Replaced by {new} of the multi-instance heater driver. Not converted by v1.18.0-rc1 (a fix is proposed in PX4/PX4-Autopilot#29354); reboot after setting it."}
       for old, new in (("SENS_IMU_TEMP", "HEATER1_TEMP"), ("SENS_IMU_TEMP_FF", "HEATER1_TEMP_FF"),
                        ("SENS_IMU_TEMP_I", "HEATER1_TEMP_I"), ("SENS_IMU_TEMP_P", "HEATER1_TEMP_P"),
                        ("SENS_TEMP_ID", "HEATER1_SENS_ID"))},

    "SIM_ARSPD_FAIL": {"kind": "removed", "commit": "4b34cb8834", "note": "Simulation only; removed."},
    "SIM_BAT_ENABLE": {"kind": "replaced", "commit": "c970a822a0", "pr": 26823, "see": ["SIM_BAT_DRAIN"],
                       "note": "Simulation only. To disable the simulated battery, set SIM_BAT_DRAIN to 0."},

    **{name: {"kind": "replaced", "commit": "e52ce5c43b", "pr": 26253,
              "see": ["UAVCAN_LGT_MODE", "UAVCAN_LGT_NUM", "UAVCAN_LGT_ID0", "UAVCAN_LGT_FN0"],
              "note": "The UAVCAN light configuration was redesigned: UAVCAN_LGT_MODE, UAVCAN_LGT_NUM, UAVCAN_LGT_IDn and UAVCAN_LGT_FNn. Not converted."}
       for name in ("UAVCAN_LGT_ANTCL", "UAVCAN_LGT_LAND", "UAVCAN_LGT_NAV", "UAVCAN_LGT_STROB")},
}

# Parameters whose type changed, with the conversion the target's param_translation.cpp applies.
TYPE_RULES = {
    **{f"RC{i}_REV": {"type": "sign", "commit": "139279747e", "pr": 26833,
                      "note": "Changed from float to int32. QGroundControl cannot read the saved \"-1.000000\" into the integer parameter and sends 0 instead, which PX4 treats as not reversed. Use the corrected file, which writes -1 or 1."}
       for i in range(1, 19)},
}
