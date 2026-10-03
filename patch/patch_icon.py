"""Sets the launcher icon.

The original APK has NO mipmap launcher icon (manifest uses @android:drawable/sym_def_app_icon),
so we create res/mipmap-<density>/ic_launcher.png from app/icon/res/ and point the manifest at it.
"""
import sys, os, shutil, re
d = sys.argv[1]
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'icon', 'res')
for dens in ('mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi'):
    src = os.path.join(root, 'ic_launcher_' + dens + '.png')
    assert os.path.exists(src), src + " missing"
    dst_dir = os.path.join(d, 'res', 'mipmap-' + dens)
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copyfile(src, os.path.join(dst_dir, 'ic_launcher.png'))
mp = os.path.join(d, 'AndroidManifest.xml')
m = open(mp, encoding='utf-8').read()
m2 = re.sub(r'android:icon="[^"]*"', 'android:icon="@mipmap/ic_launcher"', m, count=1)
assert m2 != m or '@mipmap/ic_launcher' in m, "android:icon not found in manifest"
if 'android:roundIcon=' not in m2:
    m2 = m2.replace('android:icon="@mipmap/ic_launcher"', 'android:icon="@mipmap/ic_launcher" android:roundIcon="@mipmap/ic_launcher"', 1)
open(mp, 'w', encoding='utf-8').write(m2)
