// swift-tools-version:5.9
//
// VigilWatchClient — the watchOS companion's API client and decision logic.
//
// Pure Foundation by design: the package builds and tests on Linux
// (`swift build` / `swift test`) so the sandbox CI can exercise the contract,
// rotation, queue, and fuse logic; Apple-only surfaces (Keychain, WatchKit)
// are compiled in behind `canImport(Security)` / platform guards. The
// macOS build-matrix task runs the same suite under Xcode.
import PackageDescription

let package = Package(
    name: "VigilWatchClient",
    platforms: [
        .watchOS(.v9),
        .macOS(.v13),
    ],
    products: [
        .library(name: "VigilWatchClient", targets: ["VigilWatchClient"])
    ],
    targets: [
        .target(name: "VigilWatchClient"),
        .testTarget(
            name: "VigilWatchClientTests",
            dependencies: ["VigilWatchClient"],
            resources: [
                .copy("Fixtures")
            ]
        ),
    ]
)
