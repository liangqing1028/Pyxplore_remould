"""Portable projects with immutable imported inputs and separate run folders."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Project:
    def __init__(self, path: Path, data: dict):
        self.path = path.resolve()
        self.root = self.path.parent
        self.data = data

    @classmethod
    def create(cls, path, name=None):
        path = Path(path).expanduser().resolve()
        if path.exists():
            raise FileExistsError("项目文件已经存在，请选择新位置或打开已有项目。")
        project = cls(path, {"format": 1, "name": name or path.stem,
                             "created_at": timestamp(), "assets": [], "runs": []})
        project.save()
        return project

    @classmethod
    def open(cls, path):
        path = Path(path).expanduser().resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != 1:
            raise ValueError("不支持的项目格式。")
        if not isinstance(data.get("assets"), list) or not isinstance(data.get("runs"), list):
            raise ValueError("项目缺少数据或分析记录。")
        project = cls(path, data)
        for asset in data["assets"]:
            project.resolve(asset["path"])
        for run in data["runs"]:
            project.resolve(run["path"])
        return project

    def resolve(self, relative):
        if Path(relative).is_absolute():
            raise ValueError("项目中的文件必须使用相对路径。")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("项目文件路径超出了项目目录。")
        return path

    def save(self):
        write_json(self.path, self.data)

    def import_file(self, source):
        source = Path(source).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("请选择文件。")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        for asset in self.data["assets"]:
            if asset["sha256"] == digest and (asset["name"] == source.name or Path(asset["path"]).name == source.name):
                existing = self.resolve(asset["path"])
                if existing.is_file() and hashlib.sha256(existing.read_bytes()).hexdigest() == digest:
                    return asset
        relative = Path("inputs") / f"{uuid4().hex[:10]}_{source.name}"
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.unlink()
            raise OSError("文件在导入过程中发生变化，请重新导入。")
        asset = {"id": uuid4().hex, "name": source.name, "path": relative.as_posix(),
                 "sha256": digest, "imported_at": timestamp()}
        self.data["assets"].append(asset)
        self.save()
        return asset

    def create_run(self, operation, parameters, inputs, seed=42, context=None):
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        directory = self.resolve(Path("runs") / run_id)
        directory.mkdir(parents=True)
        if context:
            context = Path(context).resolve(strict=True)
            if not context.is_relative_to(self.root / "runs") or context == directory:
                raise ValueError("前次结果必须是本项目中的已有分析。")
            shutil.copytree(context, directory / "context", ignore=shutil.ignore_patterns("context", "inputs", "run.log"))
        staged = {}
        input_records = {}
        for key, paths in inputs.items():
            multiple = isinstance(paths, list)
            staged_files = []
            records = []
            for index, value in enumerate(paths if multiple else [paths]):
                asset = self.import_file(value)
                source = self.resolve(asset["path"])
                target = directory / "inputs" / key / str(index) / Path(asset["name"]).name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                staged_files.append(target.relative_to(directory).as_posix())
                records.append({"name": asset["name"], "sha256": asset["sha256"]})
            staged[key] = staged_files if multiple else staged_files[0]
            input_records[key] = records if multiple else records[0]
        request = {"format": 1, "operation": operation, "parameters": parameters,
                   "inputs": staged, "input_records": input_records, "seed": seed}
        write_json(directory / "request.json", request)
        run = {"id": run_id, "operation": operation,
               "path": directory.relative_to(self.root).as_posix(),
               "created_at": timestamp(), "status": "queued"}
        self.data["runs"].append(run)
        self.save()
        return directory

    def update_run(self, directory, status):
        relative = Path(directory).resolve().relative_to(self.root).as_posix()
        for run in self.data["runs"]:
            if run["path"] == relative:
                run["status"] = status
                run["finished_at"] = timestamp()
                break
        self.save()
