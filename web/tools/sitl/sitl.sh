#!/bin/sh
# usage: sitl.sh start|stop <worktree> <workdir>
B="$2/build/px4_sitl_default"
case "$1" in
  start) mkdir -p "$3" && cd "$3" && ulimit -S -n 2048 && PX4_SIM_MODEL=sihsim_quadx PX4_SIMULATOR=sihsim nohup "$B/bin/px4" -d "$B/etc" > "$3.log" 2>&1 &
         for i in $(seq 1 150); do grep -q "Startup script returned successfully" "$3.log" 2>/dev/null && break; sleep 1; done; grep -c "Startup script returned successfully" "$3.log";;
  stop) cd "$3" && "$B/bin/px4-shutdown"; sleep 2; pgrep -x px4 >/dev/null && echo "still running" || echo stopped;;
esac
