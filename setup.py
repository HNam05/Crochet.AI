"""Bundle the authoritative schema directory without maintaining a second source copy."""

from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithSchemas(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "crochet_ai" / "schemas"
        destination.mkdir(parents=True, exist_ok=True)
        for source in sorted((Path(__file__).parent / "schemas").glob("*.schema.json")):
            copy2(source, destination / source.name)
        profiles_destination = Path(self.build_lib) / "crochet_ai" / "profiles"
        profiles_destination.mkdir(parents=True, exist_ok=True)
        copy2(
            Path(__file__).parent / "profiles" / "v0-mesh-numeric-profile-1.json",
            profiles_destination / "v0-mesh-numeric-profile-1.json",
        )


setup(cmdclass={"build_py": BuildWithSchemas})
