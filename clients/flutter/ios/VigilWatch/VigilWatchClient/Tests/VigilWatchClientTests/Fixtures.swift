import Foundation

/// Loads the fixture JSONs committed beside the tests. The fixtures are
/// derived from `core/api/v1/contract.snapshot.json` — the frozen contract —
/// so decode tests pin the client to the server's actual wire shapes.
enum Fixtures {
    static func data(_ resource: String) -> Data {
        let url = Bundle.module.url(
            forResource: resource,
            withExtension: "json",
            subdirectory: "Fixtures"
        )
        guard let url else {
            fatalError("fixture missing: \(resource).json")
        }
        return try! Data(contentsOf: url)
    }
}
