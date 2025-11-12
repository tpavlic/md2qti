on open droppedFiles
	set bundlePath to POSIX path of (path to me)
	set scriptPath to bundlePath & "Contents/Resources/Scripts/md2t2qti.py"

	repeat with f in droppedFiles -- f is an alias
		set filePosix to POSIX path of f

		-- Get parent folder and filename via System Events
		tell application "System Events"
			set parentAlias to container of f
			set parentDir to POSIX path of parentAlias
			set fileName to name of f
		end tell

		-- Basename without last extension
		set nameParts to my splitText(fileName, ".")
		if (count of nameParts) > 1 then
			set baseName to (items 1 thru -2 of nameParts) as text
		else
			set baseName to fileName
		end if

		-- Full output path in same folder
		set outPath to parentDir & "/" & baseName & ".txt"

		-- Build command and merge stderr into stdout (2>&1)
		set cmd to "/usr/bin/env python3 " & scriptPath & " " & quoted form of filePosix & " -o " & quoted form of outPath & " && text2qti " & quoted form of outPath

		try
			-- Run under zsh with login shell so PATH/Homebrew are available
			set outputText to do shell script "/bin/zsh -lc " & quoted form of cmd & " 2>&1"
			if outputText is "" then set outputText to "(no output)"
			display dialog "? Finished: " & baseName & return & return & outputText buttons {"OK"} default button 1
		on error errMsg number errNum
			display dialog "? Failed: " & baseName & " (error " & errNum & ")" & return & return & errMsg buttons {"OK"} default button 1
		end try
	end repeat
end open

on run
	set pickedFile to choose file with prompt "Select a file to process:"
	open {pickedFile}
end run

on splitText(theText, theDelimiter)
	set {oldTIDs, text item delimiters} to {text item delimiters, theDelimiter}
	set theItems to text items of theText
	set text item delimiters to oldTIDs
	return theItems
end splitText