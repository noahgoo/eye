from py2app import build_app as _ba

# setuptools populates install_requires from pyproject.toml; py2app rejects it.
# Patch py2app's finalize_options to clear install_requires before its check runs.
_orig_finalize = _ba.py2app.finalize_options


def _patched_finalize(self):
    self.distribution.install_requires = []
    _orig_finalize(self)


_ba.py2app.finalize_options = _patched_finalize

from setuptools import setup

APP = ["eye_app.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["eye"],
    "plist": {
        "CFBundleName": "Eye",
        "CFBundleDisplayName": "Eye",
        "CFBundleIdentifier": "com.noahgoo.eye",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        # NO LSUIElement — required so dynamic setActivationPolicy_ works.
        # With LSUIElement=YES, activateIgnoringOtherApps_ silently fails.
        "NSApplicationSupportsSecureRestorableState": True,
    },
}

setup(
    name="Eye",
    app=APP,
    data_files=[],
    options={"py2app": OPTIONS},
)
