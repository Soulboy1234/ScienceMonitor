on run
	set currentScriptPath to POSIX path of (path to me)
	set scriptDir to do shell script "/usr/bin/dirname " & quoted form of currentScriptPath
	set scriptPath to scriptDir & "/start_panel.sh"
	do shell script "/bin/bash " & quoted form of scriptPath & " >/dev/null 2>&1 &"
end run
