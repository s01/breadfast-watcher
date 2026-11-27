"""Build a native menu-bar app using the Mac's Swift compiler (no packages)."""
import pathlib, plistlib, shutil, subprocess, sys

HERE=pathlib.Path(__file__).resolve().parent
destination=pathlib.Path(sys.argv[1]).expanduser().resolve()
contents=destination/'Contents';binary=contents/'MacOS';resources=contents/'Resources'
binary.mkdir(parents=True,exist_ok=True);resources.mkdir(parents=True,exist_ok=True)
subprocess.run(['swiftc','-swift-version','5',str(HERE/'BreadfastLocal.swift'),'-o',str(binary/'BreadfastLocal'),'-framework','AppKit','-framework','UserNotifications'],check=True)
for source in [HERE/'local_worker.py',HERE/'local_history.py',HERE.parent/'scan.py',HERE.parent/'catalogue_sources.py',HERE.parent/'catalogue_http.py',HERE.parent/'promotion_sources.py']:
    shutil.copy2(source,resources/source.name)
info={'CFBundleIdentifier':'com.saif.breadfast.local','CFBundleName':'Breadfast Local',
      'CFBundleDisplayName':'Breadfast Local','CFBundleExecutable':'BreadfastLocal',
      'CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.0','CFBundleVersion':'1',
      'LSUIElement':True,'LSMinimumSystemVersion':'13.0',
      'NSHumanReadableCopyright':'Local personal discount monitor'}
with (contents/'Info.plist').open('wb') as f:plistlib.dump(info,f)
subprocess.run(['codesign','--force','--sign','-',str(destination)],check=True)
print(destination)
