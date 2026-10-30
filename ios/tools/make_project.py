#!/usr/bin/env python3
"""Write ios/Pearl.xcodeproj from the files in ios/Pearl.

Run it after adding or removing a Swift file:

    python3 ios/tools/make_project.py

Every .swift file under ios/Pearl is compiled; Assets.xcassets and the fonts
in Fonts/ are the resources. The signing team already chosen in Xcode is kept.
IDs are derived from paths, so running it twice gives the same
project and git diffs stay small. Works with Xcode 14 and later.
"""

from __future__ import annotations

import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
IOS = os.path.dirname(HERE)
APP = "Pearl"
SRC = os.path.join(IOS, APP)
BUNDLE_ID = "com.mariapapadimitriou.pearl"
DEPLOYMENT = "16.0"


def uid(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:24].upper()


def q(s: str) -> str:
    """Quote a value when the plist format needs it."""
    if s and all(c.isalnum() or c in "._/" for c in s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def collect():
    """Swift files and the resources (the asset catalogue and the fonts), as
    paths relative to ios/Pearl."""
    swift, assets = [], []
    for root, dirs, files in os.walk(SRC):
        rel_root = os.path.relpath(root, SRC)
        if rel_root.endswith(".xcassets") or ".xcassets" in rel_root.split(os.sep):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for d in dirs:
            if d.endswith(".xcassets"):
                assets.append(os.path.normpath(os.path.join(rel_root, d)))
        for f in sorted(files):
            if f.endswith(".swift"):
                swift.append(os.path.normpath(os.path.join(rel_root, f)))
            elif f.endswith(".ttf"):
                assets.append(os.path.normpath(os.path.join(rel_root, f)))
    return sorted(swift), sorted(assets)


def team() -> str:
    """The signing team picked in Xcode (Signing & Capabilities), so running
    this again doesn't sign her out of running on her iPhone."""
    path = os.path.join(IOS, f"{APP}.xcodeproj", "project.pbxproj")
    try:
        with open(path, encoding="utf-8") as fh:
            found = re.search(r'DEVELOPMENT_TEAM = "?([A-Z0-9]+)"?;', fh.read())
    except OSError:
        return ""
    return found.group(1) if found else ""


def main() -> None:
    swift, assets = collect()
    files = swift + assets + ["Info.plist"]

    project = uid("project")
    main_group = uid("group", "")
    products_group = uid("group", "Products")
    product = uid("product", APP)
    target = uid("target", APP)
    sources_phase = uid("phase", "sources")
    resources_phase = uid("phase", "resources")
    frameworks_phase = uid("phase", "frameworks")
    project_configs = uid("configlist", "project")
    target_configs = uid("configlist", "target")

    file_ref = {f: uid("file", f) for f in files}
    build_file = {f: uid("build", f) for f in swift + assets}

    # Groups mirror the folders.
    groups: dict[str, list[str]] = {}          # group path -> child ids
    group_id = {APP: uid("group", APP)}
    groups[APP] = []

    def ensure_group(path: str) -> str:
        if path in group_id:
            return group_id[path]
        parent = os.path.dirname(path) or APP
        gid = uid("group", path)
        group_id[path] = gid
        groups[path] = []
        ensure_group(parent) if parent != path else None
        groups[parent].append(gid)
        return gid

    for f in files:
        folder = os.path.dirname(f)
        gpath = os.path.join(APP, folder) if folder else APP
        ensure_group(gpath)
        groups[gpath].append(file_ref[f])

    def file_type(f: str) -> str:
        if f.endswith(".swift"):
            return "sourcecode.swift"
        if f.endswith(".xcassets"):
            return "folder.assetcatalog"
        if f.endswith(".plist"):
            return "text.plist.xml"
        if f.endswith(".ttf"):
            return "file"
        return "text"

    out = []
    w = out.append
    w("// !$*UTF8*$!")
    w("{")
    w("\tarchiveVersion = 1;")
    w("\tclasses = {")
    w("\t};")
    w("\tobjectVersion = 56;")
    w("\tobjects = {")
    w("")
    w("/* Begin PBXBuildFile section */")
    for f in swift + assets:
        phase = "Sources" if f.endswith(".swift") else "Resources"
        name = os.path.basename(f)
        w(f"\t\t{build_file[f]} /* {name} in {phase} */ = {{isa = PBXBuildFile; "
          f"fileRef = {file_ref[f]} /* {name} */; }};")
    w("/* End PBXBuildFile section */")
    w("")
    w("/* Begin PBXFileReference section */")
    w(f"\t\t{product} /* {APP}.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; "
      f"includeInIndex = 0; path = {APP}.app; sourceTree = BUILT_PRODUCTS_DIR; }};")
    for f in files:
        name = os.path.basename(f)
        w(f"\t\t{file_ref[f]} /* {name} */ = {{isa = PBXFileReference; lastKnownFileType = {file_type(f)}; "
          f"path = {q(name)}; sourceTree = \"<group>\"; }};")
    w("/* End PBXFileReference section */")
    w("")
    w("/* Begin PBXFrameworksBuildPhase section */")
    w(f"\t\t{frameworks_phase} /* Frameworks */ = {{")
    w("\t\t\tisa = PBXFrameworksBuildPhase;")
    w("\t\t\tbuildActionMask = 2147483647;")
    w("\t\t\tfiles = (")
    w("\t\t\t);")
    w("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    w("\t\t};")
    w("/* End PBXFrameworksBuildPhase section */")
    w("")
    w("/* Begin PBXGroup section */")
    w(f"\t\t{main_group} = {{")
    w("\t\t\tisa = PBXGroup;")
    w("\t\t\tchildren = (")
    w(f"\t\t\t\t{group_id[APP]} /* {APP} */,")
    w(f"\t\t\t\t{products_group} /* Products */,")
    w("\t\t\t);")
    w("\t\t\tsourceTree = \"<group>\";")
    w("\t\t};")
    w(f"\t\t{products_group} /* Products */ = {{")
    w("\t\t\tisa = PBXGroup;")
    w("\t\t\tchildren = (")
    w(f"\t\t\t\t{product} /* {APP}.app */,")
    w("\t\t\t);")
    w("\t\t\tname = Products;")
    w("\t\t\tsourceTree = \"<group>\";")
    w("\t\t};")
    for gpath in sorted(groups):
        gid = group_id[gpath]
        name = os.path.basename(gpath)
        w(f"\t\t{gid} /* {name} */ = {{")
        w("\t\t\tisa = PBXGroup;")
        w("\t\t\tchildren = (")
        # Folders first, then files, each alphabetical.
        kids = groups[gpath]
        sub = [k for k in kids if k in group_id.values()]
        leaf = [k for k in kids if k not in group_id.values()]
        names = {v: os.path.basename(p) for p, v in group_id.items()}
        names.update({v: os.path.basename(f) for f, v in file_ref.items()})
        for k in sorted(sub, key=lambda k: names[k].lower()) + sorted(leaf, key=lambda k: names[k].lower()):
            w(f"\t\t\t\t{k} /* {names[k]} */,")
        w("\t\t\t);")
        w(f"\t\t\tpath = {q(name)};")
        w("\t\t\tsourceTree = \"<group>\";")
        w("\t\t};")
    w("/* End PBXGroup section */")
    w("")
    w("/* Begin PBXNativeTarget section */")
    w(f"\t\t{target} /* {APP} */ = {{")
    w("\t\t\tisa = PBXNativeTarget;")
    w(f"\t\t\tbuildConfigurationList = {target_configs} /* Build configuration list for PBXNativeTarget \"{APP}\" */;")
    w("\t\t\tbuildPhases = (")
    w(f"\t\t\t\t{sources_phase} /* Sources */,")
    w(f"\t\t\t\t{frameworks_phase} /* Frameworks */,")
    w(f"\t\t\t\t{resources_phase} /* Resources */,")
    w("\t\t\t);")
    w("\t\t\tbuildRules = (")
    w("\t\t\t);")
    w("\t\t\tdependencies = (")
    w("\t\t\t);")
    w(f"\t\t\tname = {APP};")
    w(f"\t\t\tproductName = {APP};")
    w(f"\t\t\tproductReference = {product} /* {APP}.app */;")
    w("\t\t\tproductType = \"com.apple.product-type.application\";")
    w("\t\t};")
    w("/* End PBXNativeTarget section */")
    w("")
    w("/* Begin PBXProject section */")
    w(f"\t\t{project} /* Project object */ = {{")
    w("\t\t\tisa = PBXProject;")
    w("\t\t\tattributes = {")
    w("\t\t\t\tBuildIndependentTargetsInParallel = 1;")
    w("\t\t\t\tLastSwiftUpdateCheck = 1500;")
    w("\t\t\t\tLastUpgradeCheck = 1500;")
    w("\t\t\t\tTargetAttributes = {")
    w(f"\t\t\t\t\t{target} = {{")
    w("\t\t\t\t\t\tCreatedOnToolsVersion = 15.0;")
    w("\t\t\t\t\t};")
    w("\t\t\t\t};")
    w("\t\t\t};")
    w(f"\t\t\tbuildConfigurationList = {project_configs} /* Build configuration list for PBXProject \"{APP}\" */;")
    w("\t\t\tcompatibilityVersion = \"Xcode 14.0\";")
    w("\t\t\tdevelopmentRegion = en;")
    w("\t\t\thasScannedForEncodings = 0;")
    w("\t\t\tknownRegions = (")
    w("\t\t\t\ten,")
    w("\t\t\t\tBase,")
    w("\t\t\t);")
    w(f"\t\t\tmainGroup = {main_group};")
    w(f"\t\t\tproductRefGroup = {products_group} /* Products */;")
    w("\t\t\tprojectDirPath = \"\";")
    w("\t\t\tprojectRoot = \"\";")
    w("\t\t\ttargets = (")
    w(f"\t\t\t\t{target} /* {APP} */,")
    w("\t\t\t);")
    w("\t\t};")
    w("/* End PBXProject section */")
    w("")
    w("/* Begin PBXResourcesBuildPhase section */")
    w(f"\t\t{resources_phase} /* Resources */ = {{")
    w("\t\t\tisa = PBXResourcesBuildPhase;")
    w("\t\t\tbuildActionMask = 2147483647;")
    w("\t\t\tfiles = (")
    for f in assets:
        w(f"\t\t\t\t{build_file[f]} /* {os.path.basename(f)} in Resources */,")
    w("\t\t\t);")
    w("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    w("\t\t};")
    w("/* End PBXResourcesBuildPhase section */")
    w("")
    w("/* Begin PBXSourcesBuildPhase section */")
    w(f"\t\t{sources_phase} /* Sources */ = {{")
    w("\t\t\tisa = PBXSourcesBuildPhase;")
    w("\t\t\tbuildActionMask = 2147483647;")
    w("\t\t\tfiles = (")
    for f in swift:
        w(f"\t\t\t\t{build_file[f]} /* {os.path.basename(f)} in Sources */,")
    w("\t\t\t);")
    w("\t\t\trunOnlyForDeploymentPostprocessing = 0;")
    w("\t\t};")
    w("/* End PBXSourcesBuildPhase section */")
    w("")

    common_project = {
        "ALWAYS_SEARCH_USER_PATHS": "NO",
        "CLANG_ENABLE_MODULES": "YES",
        "CLANG_ENABLE_OBJC_ARC": "YES",
        "COPY_PHASE_STRIP": "NO",
        "ENABLE_STRICT_OBJC_MSGSEND": "YES",
        "GCC_C_LANGUAGE_STANDARD": "gnu17",
        "IPHONEOS_DEPLOYMENT_TARGET": DEPLOYMENT,
        "SDKROOT": "iphoneos",
        "SWIFT_VERSION": "5.0",
    }
    debug_project = {**common_project,
                     "DEBUG_INFORMATION_FORMAT": "dwarf",
                     "ENABLE_TESTABILITY": "YES",
                     "GCC_OPTIMIZATION_LEVEL": "0",
                     "GCC_PREPROCESSOR_DEFINITIONS": ["DEBUG=1", "$(inherited)"],
                     "ONLY_ACTIVE_ARCH": "YES",
                     "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "DEBUG",
                     "SWIFT_OPTIMIZATION_LEVEL": "-Onone"}
    release_project = {**common_project,
                       "DEBUG_INFORMATION_FORMAT": "dwarf-with-dsym",
                       "ENABLE_NS_ASSERTIONS": "NO",
                       "SWIFT_COMPILATION_MODE": "wholemodule",
                       "SWIFT_OPTIMIZATION_LEVEL": "-O",
                       "VALIDATE_PRODUCT": "YES"}
    target_settings = {
        "ASSETCATALOG_COMPILER_APPICON_NAME": "AppIcon",
        "ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME": "AccentColor",
        "CODE_SIGN_STYLE": "Automatic",
        "CURRENT_PROJECT_VERSION": "1",
        "DEVELOPMENT_TEAM": team(),
        "ENABLE_PREVIEWS": "YES",
        "GENERATE_INFOPLIST_FILE": "YES",
        "INFOPLIST_FILE": f"{APP}/Info.plist",
        "INFOPLIST_KEY_CFBundleDisplayName": APP,
        "INFOPLIST_KEY_LSApplicationCategoryType": "public.app-category.finance",
        "INFOPLIST_KEY_UIApplicationSupportsIndirectInputEvents": "YES",
        "INFOPLIST_KEY_UILaunchScreen_Generation": "YES",
        "INFOPLIST_KEY_UISupportedInterfaceOrientations": "UIInterfaceOrientationPortrait",
        "IPHONEOS_DEPLOYMENT_TARGET": DEPLOYMENT,
        "LD_RUNPATH_SEARCH_PATHS": ["$(inherited)", "@executable_path/Frameworks"],
        "MARKETING_VERSION": "1.0",
        "PRODUCT_BUNDLE_IDENTIFIER": BUNDLE_ID,
        "PRODUCT_NAME": "$(TARGET_NAME)",
        "SWIFT_EMIT_LOC_STRINGS": "YES",
        "SWIFT_VERSION": "5.0",
        "TARGETED_DEVICE_FAMILY": "1",
    }

    def config(cid: str, name: str, settings: dict) -> None:
        w(f"\t\t{cid} /* {name} */ = {{")
        w("\t\t\tisa = XCBuildConfiguration;")
        w("\t\t\tbuildSettings = {")
        for k in sorted(settings):
            v = settings[k]
            if isinstance(v, list):
                w(f"\t\t\t\t{k} = (")
                for item in v:
                    w(f"\t\t\t\t\t{q(item)},")
                w("\t\t\t\t);")
            else:
                w(f"\t\t\t\t{k} = {q(v)};")
        w("\t\t\t};")
        w(f"\t\t\tname = {name};")
        w("\t\t};")

    configs = {
        ("project", "Debug"): uid("config", "project", "Debug"),
        ("project", "Release"): uid("config", "project", "Release"),
        ("target", "Debug"): uid("config", "target", "Debug"),
        ("target", "Release"): uid("config", "target", "Release"),
    }
    w("/* Begin XCBuildConfiguration section */")
    config(configs[("project", "Debug")], "Debug", debug_project)
    config(configs[("project", "Release")], "Release", release_project)
    config(configs[("target", "Debug")], "Debug", target_settings)
    config(configs[("target", "Release")], "Release", target_settings)
    w("/* End XCBuildConfiguration section */")
    w("")
    w("/* Begin XCConfigurationList section */")
    for lid, owner, label in ((project_configs, "project", f"PBXProject \"{APP}\""),
                              (target_configs, "target", f"PBXNativeTarget \"{APP}\"")):
        w(f"\t\t{lid} /* Build configuration list for {label} */ = {{")
        w("\t\t\tisa = XCConfigurationList;")
        w("\t\t\tbuildConfigurations = (")
        w(f"\t\t\t\t{configs[(owner, 'Debug')]} /* Debug */,")
        w(f"\t\t\t\t{configs[(owner, 'Release')]} /* Release */,")
        w("\t\t\t);")
        w("\t\t\tdefaultConfigurationIsVisible = 0;")
        w("\t\t\tdefaultConfigurationName = Release;")
        w("\t\t};")
    w("/* End XCConfigurationList section */")
    w("\t};")
    w(f"\trootObject = {project} /* Project object */;")
    w("}")

    proj_dir = os.path.join(IOS, f"{APP}.xcodeproj")
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "project.pbxproj"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    # A shared scheme, so "Pearl" is there to run the first time it opens.
    scheme_dir = os.path.join(proj_dir, "xcshareddata", "xcschemes")
    os.makedirs(scheme_dir, exist_ok=True)
    ref = (f'<BuildableReference BuildableIdentifier = "primary" BlueprintIdentifier = "{target}" '
           f'BuildableName = "{APP}.app" BlueprintName = "{APP}" '
           f'ReferencedContainer = "container:{APP}.xcodeproj"></BuildableReference>')
    scheme = f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion = "1500" version = "1.7">
   <BuildAction parallelizeBuildables = "YES" buildImplicitDependencies = "YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting = "YES" buildForRunning = "YES" buildForProfiling = "YES" buildForArchiving = "YES" buildForAnalyzing = "YES">
            {ref}
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction buildConfiguration = "Debug" selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv = "YES">
   </TestAction>
   <LaunchAction buildConfiguration = "Debug" selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB" launchStyle = "0" useCustomWorkingDirectory = "NO" ignoresPersistentStateOnLaunch = "NO" debugDocumentVersioning = "YES" debugServiceExtension = "internal" allowLocationSimulation = "YES">
      <BuildableProductRunnable runnableDebuggingMode = "0">
         {ref}
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration = "Release" shouldUseLaunchSchemeArgsEnv = "YES" savedToolIdentifier = "" useCustomWorkingDirectory = "NO" debugDocumentVersioning = "YES">
      <BuildableProductRunnable runnableDebuggingMode = "0">
         {ref}
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction buildConfiguration = "Debug">
   </AnalyzeAction>
   <ArchiveAction buildConfiguration = "Release" revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
"""
    with open(os.path.join(scheme_dir, f"{APP}.xcscheme"), "w", encoding="utf-8") as fh:
        fh.write(scheme)
    print(f"Wrote {APP}.xcodeproj: {len(swift)} Swift files, {len(assets)} resource(s).")


if __name__ == "__main__":
    main()
