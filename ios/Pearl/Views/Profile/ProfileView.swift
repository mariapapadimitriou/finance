import PhotosUI
import SwiftUI

/// P-01 Profile (THL-104, THL-209, THL-120): who's signed in, then Money,
/// You, Privacy and Help, each row led by its icon, and Sign out under them.
/// Everything opens in the app; nothing sends her to the web.
///
/// A+ (REDESIGN-03, AP-Profile): pushed from the profile circle in the
/// current tab, with Back. The header is her avatar with Add photo / Change
/// photo, her name and her email; it no longer opens Sign-in and security
/// (that row stays under You).
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var photos = ProfilePhotoStore.shared
    /// Your data's and Privacy's "Go to Home": pops Profile, then Home.
    let goHome: () -> Void
    @State private var summary: ProfileSummary?
    // The photo (AP-PhotoSheet → AP-Crop, G5-Photo).
    @State private var photoSheet = false
    @State private var afterSheet: PhotoChoice?
    @State private var choosing = false
    @State private var picked: PhotosPickerItem?
    @State private var taking = false
    @State private var cropping: CropImage?
    @State private var saving = false
    @State private var toast: PearlToast.Model?
    /// P-01: "Every 2 weeks · 5 bills".
    @State private var doc: PearlDoc?
    @State private var showYourData = false
    @State private var showConsent = false
    @AppStorage(Appearance.key) private var appearance = Appearance.automatic.rawValue
    @State private var confirmSignOut = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                backButton.padding(.top, 4)
                Text("Profile").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.bottom, 8)

                identity.padding(.bottom, 8)

                ProfileSection("Money")
                APCard {
                    NavigationLink { AccountsView() } label: {
                        ProfileRow(symbol: "building.columns", title: "Accounts",
                                   pill: summary?.needsYou.flatMap { $0 > 0 ? StatusPill(text: "\($0) needs you", tone: .needsALook) : nil })
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    NavigationLink { IncomeBillsView() } label: {
                        ProfileRow(symbol: "dollarsign.square", title: "Income and bills")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    NavigationLink { RecurringTransfersView() } label: {
                        ProfileRow(symbol: "arrow.triangle.2.circlepath", title: "Recurring transfers")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    // THL-128: Debts has its own row, not only Set Pearl up again's step.
                    NavigationLink { DebtsView() } label: {
                        ProfileRow(symbol: "creditcard", title: "Debts")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    NavigationLink { CategoriesRulesView() } label: {
                        ProfileRow(symbol: "square.on.circle", title: "Categories and rules")
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("You")
                APCard {
                    NavigationLink { SignInSecurityView() } label: {
                        ProfileRow(symbol: "lock", title: "Sign-in and security")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    NavigationLink { NotificationsView() } label: {
                        ProfileRow(symbol: "bell", title: "Notifications")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    appearanceRow
                }

                ProfileSection("Privacy")
                APCard {
                    Button { showConsent = true } label: {
                        ProfileRow(symbol: "eye", title: "Privacy and consent")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    Button { showYourData = true } label: {
                        ProfileRow(symbol: "tray.and.arrow.down", title: "Your data")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    NavigationLink { ProtectView() } label: {
                        ProfileRow(symbol: "checkmark.shield", title: "How we protect you")
                    }
                    .buttonStyle(.plain)
                }

                APCard {
                    Button { doc = .help } label: {
                        ProfileRow(symbol: "questionmark.circle", title: "Help and support")
                    }
                    .buttonStyle(.plain)
                    APSeparator()
                    // THL-118: the Terms, after sign-up too.
                    Button { doc = .terms } label: {
                        ProfileRow(symbol: "doc.text", title: "Terms")
                    }
                    .buttonStyle(.plain)
                }
                .padding(.top, 12)

                Button("Sign out") { confirmSignOut = true }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)


                ProfileNote("Pearl for iPhone · \(version)", centred: true)
                    .padding(.top, 12)
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .refreshable { await load() }
        .nacreScreen()
        .navigationBarHidden(true)
        .reloads { await load() }
        .docSheet($doc)
        .navigationDestination(isPresented: $showConsent) {
            ConsentView(goHome: {
                showConsent = false
                goHome()
            })
        }
        .navigationDestination(isPresented: $showYourData) {
            YourDataView(goHome: {
                showYourData = false
                goHome()
            })
        }
        .sheet(isPresented: $photoSheet, onDismiss: runChoice) {
            PhotoOptionsSheet(initials: initials, photo: photos.image, pick: { choice in
                afterSheet = choice
                photoSheet = false
            }, onClose: { photoSheet = false })
        }
        .photosPicker(isPresented: $choosing, selection: $picked, matching: .images)
        .onChange(of: picked) { item in
            guard let item = item else { return }
            picked = nil
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    cropping = CropImage(image: image)
                } else {
                    say("Couldn\u{2019}t open that photo.", failed: true)
                }
            }
        }
        .fullScreenCover(isPresented: $taking) {
            CameraPicker { image in
                taking = false
                if let image = image {
                    // After the camera has gone, so the crop can come up.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { cropping = CropImage(image: image) }
                }
            }
            .ignoresSafeArea()
        }
        .fullScreenCover(item: $cropping) { c in
            PhotoCropView(image: c.image, use: { cropped in
                cropping = nil
                Task { await save(cropped) }
            }, cancel: { cropping = nil })
        }
        .overlay(alignment: .bottom) {
            if let toast = toast {
                PearlToast(model: toast) { if self.toast == toast { withAnimation { self.toast = nil } } }
                    .padding(.bottom, 12)
                    .id(toast.id)
            }
        }
        .sheet(isPresented: $confirmSignOut) {
            // P-05 (TEST-06): a Pearl sheet, not an action sheet.
            PearlConfirmSheet(overline: "Sign out", title: "Sign out on this iPhone?",
                              message: "Pearl stays as it is. To come back, you’ll sign in again.",
                              primary: "Sign out", busyLabel: "Signing out…", secondary: "Stay signed in",
                              failure: "Couldn’t sign out. Try again.",
                              onClose: { confirmSignOut = false }) {
                confirmSignOut = false
                await app.signOut()
            }
        }
    }

    // MARK: Parts

    /// The 44 pt glass Back circle on a pushed page.
    private var backButton: some View {
        Button { dismiss() } label: {
            Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Nacre.glass))
                .overlay(Circle().strokeBorder(Nacre.glassEdge, lineWidth: 1))
                .shadow(color: Color(hex: 0x1C1A33).opacity(0.1), radius: 5, y: 6)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Back")
        .accessibilityIdentifier("profile-back")
    }

    /// AP-Profile: the avatar (92, nacre ring; initials or her photo), Add
    /// photo / Change photo (G5-Photo: "Saving…" with the ring filling), her
    /// name in Fraunces and her email.
    private var identity: some View {
        VStack(spacing: 6) {
            ProfileAvatar(initials: initials, photo: photos.image, size: 92, ring: 1.5,
                          font: .custom("Figtree-SemiBold", size: 28, relativeTo: .title))
                .overlay { if saving { SavingRing(size: 92) } }
                .accessibilityHidden(true)
            Button(saving ? "Saving\u{2026}" : (photos.image == nil ? "Add photo" : "Change photo")) {
                photoSheet = true
            }
            .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
            .foregroundColor(Pearl.link)
            .buttonStyle(.plain)
            .frame(minHeight: 44)
            .disabled(saving)
            .accessibilityIdentifier("profile-photo")
            VStack(spacing: 2) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(1)
                    .accessibilityAddTraits(.isHeader)
                if let email = app.user?.email, !email.isEmpty {
                    Text(email).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: The photo

    /// The sheet has gone: now the picker, the camera, or Remove.
    private func runChoice() {
        guard let choice = afterSheet else { return }
        afterSheet = nil
        switch choice {
        case .choose:
            // PHPicker: runs outside Pearl, so it never needs Photos access.
            choosing = true
        case .take:
            Task {
                if await CameraAccess.allowed() {
                    taking = true
                } else {
                    // REDESIGN-16: the ink toast; Settings opens Pearl's page in iOS Settings.
                    toast = PearlToast.Model(text: "Camera is off for Pearl", action: "Settings", failed: true) {
                        toast = nil
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            UIApplication.shared.open(url)
                        }
                    }
                }
            }
        case .remove:
            photos.remove()
        }
    }

    /// G5-Photo: the ring fills while it saves; "Couldn’t save your photo."
    /// with Try again if it can't.
    private func save(_ photo: UIImage) async {
        saving = true
        defer { saving = false }
        // The ring's fill (0.6 s) is what she sees; the write itself is quick.
        try? await Task.sleep(nanoseconds: 600_000_000)
        do {
            try photos.save(photo)
        } catch {
            toast = PearlToast.Model(text: "Couldn\u{2019}t save your photo.", action: "Try again", failed: true) {
                toast = nil
                Task { await save(photo) }
            }
        }
    }

    private func say(_ text: String, failed: Bool) {
        toast = PearlToast.Model(text: text, failed: failed)
    }

    /// "Appearance   Automatic ›": Automatic, Light or Dark, on this iPhone.
    private var appearanceRow: some View {
        Menu {
            Picker("Appearance", selection: $appearance) {
                ForEach(Appearance.allCases) { Text($0.title).tag($0.rawValue) }
            }
        } label: {
            ProfileRow(symbol: "moon", title: "Appearance") {
                Text(Appearance(rawValue: appearance)?.title ?? Appearance.automatic.title)
                    .font(Nacre.body).foregroundColor(Pearl.muted)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Appearance")
        .accessibilityValue(Appearance(rawValue: appearance)?.title ?? Appearance.automatic.title)
    }

    /// Reset Pearl: back to the start of setup, keeping the sign-in.
    // MARK: Words

    private var name: String { ProfileName.name(app.user) }

    /// "M" from Maya (first name only, REDESIGN-16), or her email's first letter.
    private var initials: String { ProfileName.initials(app.user) }

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    // MARK: Calls

    /// Only the Accounts row's "needs you" needs the server now (2026-11-08):
    /// the rows have no second lines.
    private func load() async {
        do {
            summary = try await app.api.get("api/profile")
        } catch {
            _ = app.handle(error)
        }
    }

}

/// A photo waiting for Move and scale.
struct CropImage: Identifiable {
    let id = UUID()
    let image: UIImage
}

/// Light or dark, or whichever the iPhone is set to (P-01's Appearance).
enum Appearance: String, CaseIterable, Identifiable {
    case automatic, light, dark

    static let key = "pearl.appearance"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .automatic: return "Automatic"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    var scheme: ColorScheme? {
        switch self {
        case .automatic: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}
