import SwiftUI

/// Watch-side port of the console's canonical tokens
/// (`docs/design/console/tokens/tokens.css`). Dark-first, same hex values,
/// same severity and level colors. The watch renders one theme (dark) —
/// ambient readability beats a scheme toggle on a 40 mm display.
enum VigilWatchTheme {
    /// Page surface — `--bg0 #141414`.
    static let bg = Color(red: 0x14 / 255, green: 0x14 / 255, blue: 0x14 / 255)
    /// Card interior — `--bg2 #212121`.
    static let card = Color(red: 0x21 / 255, green: 0x21 / 255, blue: 0x21 / 255)
    /// Hover/press surface — `--bg3 #292929`.
    static let cardPressed = Color(red: 0x29 / 255, green: 0x29 / 255, blue: 0x29 / 255)
    /// Hairline — `--ln1 #303030`.
    static let hairline = Color(red: 0x30 / 255, green: 0x30 / 255, blue: 0x30 / 255)
    /// Primary text — `--tx0 #F5F5F5`.
    static let text = Color(red: 0xF5 / 255, green: 0xF5 / 255, blue: 0xF5 / 255)
    /// Meta text — `--tx2 #9E9E9E`.
    static let textMeta = Color(red: 0x9E / 255, green: 0x9E / 255, blue: 0x9E / 255)

    /// Accent — `--accent #3AA8FF` (dark scheme value).
    static let accent = Color(red: 0x3A / 255, green: 0xA8 / 255, blue: 0xFF / 255)

    /// "Needs you" and destructive — Poor `#FF3B5C`.
    static let poor = Color(red: 0xFF / 255, green: 0x3B / 255, blue: 0x5C / 255)
    /// Warning band — Fair `#FFB300`.
    static let fair = Color(red: 0xFF / 255, green: 0xB3 / 255, blue: 0x00 / 255)
    /// Healthy band — Good `#00E676`.
    static let good = Color(red: 0x00 / 255, green: 0xE6 / 255, blue: 0x76 / 255)

    /// DeepTempo brand — `--dt-red #D92424` (splash/app-icon surfaces).
    static let brandRed = Color(red: 0xD9 / 255, green: 0x24 / 255, blue: 0x24 / 255)

    /// Chip color for a raw `reversibility` value from the frozen
    /// contract: green when the action can be taken back, Poor-red when it
    /// cannot (Poor doubles as "Needs you" and destructive in the console
    /// tokens), Fair for anything unrecognized.
    static func chipColor(for reversibility: String) -> Color {
        switch reversibility {
        case "reversible": return good
        case "irreversible": return poor
        default: return fair
        }
    }
}
