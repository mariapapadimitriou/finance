import SwiftUI
import UIKit

// A+ navigation (REDESIGN-02, -03; AP-Home, AP-CashFlow, AP-PhotoHome,
// AP-Profile; Pearl Design System `ProfileCircle`). Profile leaves the tab
// bar for this circle at the top right of every main tab: Home, Cash flow,
// Save, Wins and Pearl. It pushes Profile in the current tab's navigation
// stack. Every tab places it with `profileCircleSlot`, never by hand, so it
// sits in the same spot on all five and doesn't move between them.

/// Her profile photo, kept on this iPhone only: a JPEG in Application
/// Support, excluded from iCloud backup, never sent to Pearl's server. One
/// file per account, so another account on the same iPhone doesn't see it.
@MainActor
final class ProfilePhotoStore: ObservableObject {
    static let shared = ProfilePhotoStore()

    @Published private(set) var image: UIImage?
    private var owner: String?

    /// Which account's photo to show (called when she signs in or out).
    func use(account: String?) {
        guard account != owner else { return }
        owner = account
        image = account.flatMap { Self.url(for: $0) }.flatMap { try? Data(contentsOf: $0) }.flatMap(UIImage.init(data:))
    }

    /// Saves the cropped photo. Throws when the file can't be written.
    func save(_ photo: UIImage) throws {
        guard let owner = owner, let url = Self.url(for: owner),
              let data = photo.jpegData(compressionQuality: 0.85) else { throw CocoaError(.fileWriteUnknown) }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        var noBackup = URLResourceValues()
        noBackup.isExcludedFromBackup = true
        var marked = url
        try? marked.setResourceValues(noBackup)
        image = photo
    }

    func remove() {
        if let owner = owner, let url = Self.url(for: owner) { try? FileManager.default.removeItem(at: url) }
        image = nil
    }

    /// The account is gone (deleted): its photo goes too.
    func forget(account: String) {
        if let url = Self.url(for: account) { try? FileManager.default.removeItem(at: url) }
        if account == owner { image = nil }
    }

    private static func url(for account: String) -> URL? {
        let safe = account.filter { $0.isLetter || $0.isNumber }
        guard !safe.isEmpty,
              let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        else { return nil }
        return base.appendingPathComponent("ProfilePhoto", isDirectory: true)
            .appendingPathComponent("profile-\(safe).jpg")
    }
}

/// The 36 pt circle (44 to tap): a 1.2 pt nacre ring, the disc `card` white
/// in light and #1C2459 in dark, her initials (13/600) or her photo, and a
/// 10 pt nacre dot when Profile needs her. Never a number.
struct ProfileAvatar: View {
    let initials: String
    var photo: UIImage?
    var size: CGFloat = 36
    var ring: CGFloat = 1.2
    var font: Font = .custom("Figtree-SemiBold", size: 13, relativeTo: .footnote)

    var body: some View {
        ZStack {
            Circle().fill(APlus.circleDisc)
            if let photo = photo {
                Image(uiImage: photo).resizable().scaledToFill()
            } else {
                Text(initials).font(font).foregroundColor(Pearl.ink)
            }
        }
        .frame(width: size - ring * 2, height: size - ring * 2)
        .clipShape(Circle())
        .padding(ring)
        .background(Circle().fill(APlus.nacreRing))
        .accessibilityHidden(true)
    }
}

struct ProfileCircle: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject private var photos = ProfilePhotoStore.shared
    @Environment(\.goHome) private var goHome
    @State private var open = false

    var body: some View {
        Button { open = true } label: {
            ProfileAvatar(initials: ProfileName.initials(app.user), photo: photos.image)
                .overlay(alignment: .topTrailing) {
                    if app.profileNeedsYou { NacreDot().offset(x: 1, y: -1) }
                }
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(app.profileNeedsYou ? "Profile, needs you" : "Profile")
        .accessibilityIdentifier("profile-circle")
        .navigationDestination(isPresented: $open) {
            // Your data's and Privacy's "Go to Home" pop Profile first.
            ProfileView(goHome: {
                open = false
                goHome()
            })
        }
    }
}

/// Where the profile circle sits on a main tab, the same on all five: a
/// 44 pt tap target pinned 6 below the safe area's top and 12 in from the
/// trailing edge, so the 36 pt disc's edge lines up with the 16 pt gutter.
/// Its centre, 28 below the safe area, is the middle of a 56 pt bar: Cash
/// flow's folded glass bar and the chat's inline bar put their titles on
/// that line, and the large-title rows sit level with it.
enum ProfileSlot {
    static let top: CGFloat = 6
    /// AP-CashFlow: Cash flow's title row sits 16 down (Home's 6), and the
    /// circle with it until the title folds into the bar.
    static let cashFlowTop: CGFloat = 16
    static let trailing: CGFloat = Pearl.gutter - 4
    static let size: CGFloat = 44
    /// From the screen's trailing edge to the circle's leading edge: what a
    /// bar drawn under the circle leaves free on its right.
    static let clearance: CGFloat = trailing + size
}

extension View {
    /// The profile circle, pinned top right over a main tab's root view
    /// (inside its NavigationStack, so it pushes Profile there). It doesn't
    /// scroll or fold with the page, and a pushed page or a sheet covers it.
    /// `shown: false` takes it away (Cash flow's Select); `enabled: false`
    /// keeps it but not tappable (a trip's pick).
    func profileCircleSlot(shown: Bool = true, enabled: Bool = true, top: CGFloat = ProfileSlot.top) -> some View {
        overlay(alignment: .topTrailing) {
            if shown {
                ProfileCircle()
                    .disabled(!enabled)
                    .padding(.top, top)
                    .padding(.trailing, ProfileSlot.trailing)
            }
        }
    }
}

/// Her name and initials, from what the server knows (first name only:
/// one letter until she has a last name, REDESIGN-16).
enum ProfileName {
    static func name(_ user: PearlUser?) -> String {
        if let first = user?.firstName, !first.isEmpty { return first }
        if let name = user?.username, !name.isEmpty { return name }
        return "Your account"
    }

    /// "M" from Maya, "MP" from Maya Park, or the first letter of her email.
    static func initials(_ user: PearlUser?) -> String {
        initials(name: user?.firstName, email: user?.email)
    }

    /// The same from a name being typed (P-01n "Your name"'s live circle):
    /// "Maya Lin" → ML; empty → her email's first letter.
    static func initials(name: String?, email: String?) -> String {
        let typed = name?.trimmingCharacters(in: .whitespaces) ?? ""
        // An email gives one letter ("maya@example.com" is M, not ME).
        let source = typed.isEmpty ? (email ?? "") : typed
        let words = source.split { !$0.isLetter }.prefix(typed.isEmpty ? 1 : 2)
        let out = words.compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "P" : out
    }
}

private struct GoHomeKey: EnvironmentKey {
    static let defaultValue: () -> Void = {}
}

extension EnvironmentValues {
    /// Switches to the Home tab (set by MainTabs).
    var goHome: () -> Void {
        get { self[GoHomeKey.self] }
        set { self[GoHomeKey.self] = newValue }
    }
}

/// The Pearl tab's image (REDESIGN-07, -16): LogoMark in its own colours
/// (`.alwaysOriginal`, so it's never tinted), 30 × 25 as the Pearl button
/// drew it; with a suggestion, the 10 pt nacre dot top right with a 1.5 pt
/// ring in the bar's own colour. Two variants, drawn once each.
enum PearlTabIcon {
    static let plain = draw(dot: false, dark: false)
    private static let suggestingLight = draw(dot: true, dark: false)
    private static let suggestingDark = draw(dot: true, dark: true)

    static func image(suggest: Bool, dark: Bool) -> UIImage {
        suggest ? (dark ? suggestingDark : suggestingLight) : plain
    }

    private static func draw(dot: Bool, dark: Bool) -> UIImage {
        let size = CGSize(width: 32, height: 27)
        let image = UIGraphicsImageRenderer(size: size).image { ctx in
            UIImage(named: "LogoMark")?.draw(in: CGRect(x: 0, y: 2, width: 30, height: 25))
            guard dot else { return }
            let rect = CGRect(x: size.width - 10, y: 0, width: 10, height: 10)
            // The bar's own colour under the dot: the sea in dark, white in light.
            (dark ? UIColor(hex: 0x1C2F73) : UIColor.white).setFill()
            ctx.cgContext.fillEllipse(in: rect.insetBy(dx: -1.5, dy: -1.5))
            let colors = [UIColor(hex: 0xFF8FB1).cgColor, UIColor(hex: 0xC9A8FF).cgColor, UIColor(hex: 0x8FE0D4).cgColor]
            if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray,
                                         locations: [0, 0.5, 1]) {
                ctx.cgContext.saveGState()
                ctx.cgContext.addEllipse(in: rect)
                ctx.cgContext.clip()
                ctx.cgContext.drawLinearGradient(gradient, start: rect.origin,
                                                 end: CGPoint(x: rect.maxX, y: rect.maxY), options: [])
                ctx.cgContext.restoreGState()
            }
        }
        return image.withRenderingMode(.alwaysOriginal)
    }
}
