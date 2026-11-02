import LocalAuthentication
import SwiftUI
import UIKit

/// Face ID as the everyday way into Pearl on this iPhone (THL-114): the
/// iPhone passcode is the fallback, through the system prompt; an email code
/// is never asked for on everyday opens.
enum AppLock {
    /// Locks after this long in the background (THL-114: 1 minute).
    static let after: TimeInterval = 60

    /// Face ID (or Touch ID) is set up on this iPhone and allowed for Pearl.
    static var available: Bool {
        var error: NSError?
        return LAContext().canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
    }

    /// Off for Pearl in Settings, or not set up on the iPhone (O-04b).
    static var turnedOff: Bool {
        var error: NSError?
        let ok = LAContext().canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
        guard !ok, let code = error.map({ LAError.Code(rawValue: $0.code) }) else { return false }
        return code == .biometryNotAvailable || code == .biometryNotEnrolled
    }

    /// Ask for Face ID; with `passcode`, the iPhone passcode works too.
    static func unlock(passcode: Bool = false, reason: String = "Unlock Pearl") async -> Bool {
        let context = LAContext()
        context.localizedFallbackTitle = passcode ? nil : ""
        let policy: LAPolicy = passcode ? .deviceOwnerAuthentication : .deviceOwnerAuthenticationWithBiometrics
        do {
            return try await context.evaluatePolicy(policy, localizedReason: reason)
        } catch {
            return false
        }
    }
}

// MARK: - O-04 Use Face ID, O-04b Face ID is off, A-09 Face ID on this iPhone

@MainActor
struct FaceIDOfferView: View {
    enum Mode { case onboarding, newIPhone }

    @EnvironmentObject private var app: AppModel
    @Environment(\.openURL) private var openURL
    let mode: Mode
    let done: () -> Void
    @State private var off = false
    @State private var busy = false

    var body: some View {
        NacreScreen(scrolls: false) {
            if mode == .onboarding {
                ShellProgress(part: 1, name: "Your account")
            }
            MessageBlock(title: off ? "Face ID is off for Pearl" : "Use Face ID", line: line) {
                IconOrb(symbol: "faceid", size: 120)
            }
            .padding(.top, mode == .onboarding ? 0 : 40)
        } actions: {
            BottomActions {
                if off {
                    Button("Open Settings") {
                        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                    }
                    .buttonStyle(NacreButtonStyle())
                } else {
                    Button("Turn on Face ID") { Task { await turnOn() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                }
            } secondary: {
                Button("Not now") { done() }
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        // Once the account exists there's no going back to the code (THL-119).
        .navigationBarBackButtonHidden(mode == .onboarding)
        .onAppear { off = AppLock.turnedOff }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
            // Back from Settings with Face ID turned on: offer it again.
            if off && AppLock.available { off = false }
        }
    }

    private var line: String {
        if off {
            return "Turn it on in iPhone Settings › Face ID & Passcode. Or use your password for now."
        }
        return mode == .onboarding
            ? "Sign in quickly and securely, without your password."
            : "Turn on Face ID for this iPhone so you won’t need your password next time."
    }

    private func turnOn() async {
        busy = true
        defer { busy = false }
        // The first time, iOS asks "Do you want to allow “Pearl” to use
        // Face ID?" (O-04a); either answer carries on.
        if await AppLock.unlock(reason: "Unlock Pearl quickly and privately.") {
            app.faceIDOn = true
            done()
        } else if AppLock.turnedOff {
            off = true
        } else {
            done()
        }
    }
}

// MARK: - A-08 Pearl is locked

@MainActor
struct AppLockView: View {
    @EnvironmentObject private var app: AppModel
    @State private var trying = false

    var body: some View {
        VStack(spacing: 0) {
            Wordmark().padding(.top, 16)
            HeroShell(width: 220).padding(.top, 100)
            Text("Pearl is locked").font(Nacre.largeTitle).tracking(0.4)
                .accessibilityAddTraits(.isHeader)
                .padding(.top, 48)
            Spacer(minLength: 24)
            BottomActions {
                Button("Unlock with Face ID") { Task { await unlock(passcode: false) } }
                    .buttonStyle(NacreButtonStyle())
            } secondary: {
                Button("Use iPhone passcode") { Task { await unlock(passcode: true) } }
                    .buttonStyle(NacreTextButtonStyle())
                Button("Can’t unlock? Sign in with password") {
                    Task { await app.signOut() }
                }
                .buttonStyle(NacreTextButtonStyle())
            }
        }
        .nacreScreen()
        .task { await unlock(passcode: false) }
    }

    private func unlock(passcode: Bool) async {
        guard !trying else { return }
        trying = true
        defer { trying = false }
        if await AppLock.unlock(passcode: passcode) {
            app.locked = false
        }
    }
}
