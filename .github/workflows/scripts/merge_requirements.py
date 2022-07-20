import os
from pathlib import Path
from packaging.markers import Marker, Op, Value, Variable
from packaging.requirements import Requirement


REQUIREMENTS_FOLDER = Path(__file__).parents[3].absolute() / "requirements"
os.chdir(REQUIREMENTS_FOLDER)


def get_requirements(fp):
    return [
        Requirement(line)
        for line in fp.read().splitlines()
        if line and not line.startswith(("#", " "))
    ]


names = ["base"]
names.extend(file.stem for file in REQUIREMENTS_FOLDER.glob("extra-*.in"))
base_requirements = []

for name in names:
    # {req_name: {sys_platform: Requirement}
    input_data = {}
    all_platforms = set()
    for file in REQUIREMENTS_FOLDER.glob(f"*-{name}.txt"):
        platform_name = file.stem.split("-", maxsplit=1)[0]
        all_platforms.add(platform_name)
        with file.open(encoding="utf-8") as fp:
            requirements = get_requirements(fp)

        for req in requirements:
            platforms = input_data.setdefault(req.name, {})
            platforms[platform_name] = req

    output = base_requirements if name == "base" else []
    for req_name, platform_data in input_data.items():
        platforms = platform_data.keys()
        req = next(iter(platform_data.values()))
        if not all(value == req for value in platform_data.values()):
            raise RuntimeError(f"Incompatible requirements for {req_name}.")

        base_req = next(
            (base_req for base_req in base_requirements if base_req.name == req.name), None
        )
        if base_req is not None:
            old_base_marker = base_req.marker
            old_req_marker = req.marker
            req.marker = base_req.marker = None
            if base_req != req:
                raise RuntimeError(f"Incompatible requirements for {req_name}.")

            base_req.marker = old_base_marker
            req.marker = old_req_marker
            if base_req.marker is None or base_req.marker == req.marker:
                continue

        if len(platforms) == len(all_platforms):
            output.append(req)
            continue
        elif len(platforms) < len(all_platforms - platforms):
            platform_marker = " or ".join(
                f"sys_platform == '{platform}'" for platform in platforms
            )
        else:
            platform_marker = " and ".join(
                f"sys_platform != '{platform}'" for platform in all_platforms - platforms
            )

        if req.marker is None:
            new_marker = platform_marker
        else:
            sys_platform_markers = set()
            markers = []
            for idx, marker in enumerate(req.marker._markers):
                if marker == "or":
                    new_marker = f"({req.marker}) and ({platform_marker})"
                    break
                if marker == "and":
                    continue

                if isinstance(marker, tuple) and marker[1].value in ("==", "!="):
                    lhs, op, rhs = marker
                    if isinstance(lhs, Variable):
                        lhs_value = lhs.value
                        rhs_value = rhs.value
                    else:
                        lhs_value = rhs.value
                        rhs_value = lhs.value
                    if lhs_value == "sys_platform":
                        sys_platform_markers.add((lhs_value, op.value, rhs_value))
                        continue

                markers.append(marker)
            else:
                new_markers = []
                for marker in markers:
                    new_markers.append(marker)
                    new_markers.append("and")

                sys_platform_eq = None
                sys_platform_ne = set()
                for marker in sys_platform_markers:
                    lhs, op, rhs = marker
                    if op == "!=":
                        sys_platform_ne.add(rhs)
                        continue
                    if sys_platform_eq is not None:
                        raise RuntimeError(f"Unsatisfiable sys_platform markers for {req.name}")
                    sys_platform_eq = rhs
                if sys_platform_eq in sys_platform_ne:
                    raise RuntimeError(f"Unsatisfiable sys_platform markers for {req.name}")

                if sys_platform_eq is None:
                    platforms -= sys_platform_ne
                    if not platforms:
                        continue
                    if len(platforms) < len(all_platforms - platforms):
                        platform_marker = " or ".join(
                            f"sys_platform == '{platform}'" for platform in platforms
                        )
                    else:
                        platform_marker = " and ".join(
                            f"sys_platform != '{platform}'" for platform in all_platforms - platforms
                        )
                    new_markers.append(Marker(platform_marker)._markers)
                    new_markers.append("and")
                elif sys_platform_eq in platforms:
                    new_markers.append((Variable("sys_platform"), Op("=="), Value(sys_platform_eq)))
                    new_markers.append("and")
                else:
                    continue

                if new_markers:
                    new_markers.pop()
                req.marker._markers = new_markers
                new_marker = str(req.marker)

        req.marker = Marker(new_marker)
        if base_req is not None and base_req.marker == req.marker:
            continue

        output.append(req)

    output.sort(key=lambda req: (req.marker is not None, req.name))
    with open(f"{name}.txt", "w+", encoding="utf-8") as fp:
        for req in output:
            fp.write(str(req))
            fp.write("\n")
