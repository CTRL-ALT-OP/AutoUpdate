Auto-updater based on pulling the latest release from a GitHub repo.

data.json
```js
{
  "owner": "CTRL-ALT-OP", // The name of the owner of the repo
  "repo": "TestRepo", // The repo name
  "asset_name": "myapp-win-x64.zip", // The target asset from the release (this would allow targeting different binaries for different OS's. Unzips the target asset
  "main_exe_name": "main.exe", // The target executable name
  "state_filename": "state.json", // Track current version, this doesn't need to change
  "versions_dir_name": "versions", // The subfolder to store versions in (stores current version and 1 version older
  "version_dir_prefix": "app-", // Mostly cosmetic
  "show_update_message": true, // Displays a pop-up while updating to the latest version
  "update_message_title": "Updating to the latest version", // The popup title
  "update_message_body": "A new version of the application is available: {version}", // The popup body
  "preserve_files": ["test.txt"] // An array of files to preserve when updating (e.g. user config files, data files, etc.)
}
```

This script should be run instead of the target repo. It will update if necessary, and then run the latest version. Check out (this repo)[https://github.com/CTRL-ALT-OP/Projector_controller] for an example use case. This means that every time your user runs the application, it will automatically check for any new releases and download the latest one if necessary. To update the app, all you have to do is create a new GitHub release and ensure your frozen binaries are packaged however your data.json config is set up. 
In the starter data.json config, you must zip the binaries as `myapp-win-x64.zip`, and upload that to the new release.


Currently, only Windows is supported, but it should be easy to set it up with other OS's with a couple of command changes.
You can download the Windows executable from [https://github.com/CTRL-ALT-OP/AutoUpdate/releases]. It will be ready to use once downloaded, and you just have to change data.json to match your app. An initial version of the app is not required; if none is found, it will automatically download the latest.
