on run
	set scriptPath to "/Users/liwenbo/Documents/codex/ScienceMonitor/scripts/launchers/start_panel.sh"
	do shell script "/bin/bash " & quoted form of scriptPath & " >/dev/null 2>&1 &"
end run
