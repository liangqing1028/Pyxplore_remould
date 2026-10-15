"""Package the already verified application on its native operating system."""

import os
import platform
import shutil
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist"
    if platform.system() == "Darwin":
        app = dist / "PyWPEMDesktop.app"
        if not (app / "Contents/MacOS/PyWPEMDesktop").is_file():
            raise FileNotFoundError("请先完成应用构建和验证。")
        stage = root / "build/dmg-stage"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        shutil.copytree(app, stage / app.name, symlinks=True, copy_function=os.link)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        image = dist / f"PyWPEMDesktop-macOS-{platform.machine()}.dmg"
        subprocess.run(["hdiutil", "create", "-volname", "PyWPEM Desktop", "-srcfolder", str(stage),
                        "-ov", "-format", "UDZO", str(image)], check=True)
        subprocess.run(["hdiutil", "verify", str(image)], check=True)
        print("安装镜像：", image)
    elif platform.system() == "Windows":
        app = dist / "PyWPEMDesktop"
        if not (app / "PyWPEMDesktop.exe").is_file():
            raise FileNotFoundError("请先完成应用构建和验证。")
        archive = shutil.make_archive(str(dist / "PyWPEMDesktop-Windows-x64"), "zip", dist, app.name)
        print("便携版（解压后双击运行）：", archive)
        compiler = shutil.which("ISCC") or str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe")
        if Path(compiler).is_file():
            subprocess.run([compiler, str(root / "packaging/windows.iss")], check=True)
        else:
            print("如需 Setup 安装程序，请安装 Inno Setup 6 后重新运行本脚本。")
    else:
        raise RuntimeError("请在 Windows 或 macOS 上制作安装包。")


if __name__ == "__main__":
    main()
