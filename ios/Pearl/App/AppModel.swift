import Foundation
import SwiftUI

/// Who is signed in, and the one connection to Pearl's server.
@MainActor
final class AppModel: ObservableObject {
    enum Phase: Equatable {
        case starting
        case signedOut
        case signedIn(PearlUser?)
    }

    @Published var phase: Phase = .starting
    /// Bumped after any change, so every screen reloads what it shows.
    @Published var version = 0

    let api = APIClient()

    /// On launch: is the saved session still good?
    func start() async {
        do {
            let status: AuthStatus = try await api.get("api/auth/status")
            phase = status.signedIn ? .signedIn(status.user) : .signedOut
        } catch {
            phase = .signedOut
        }
    }

    func signedIn(_ user: PearlUser?) {
        phase = .signedIn(user)
        version += 1
    }

    func changed() {
        version += 1
    }

    /// Any call that comes back "signed out" lands here.
    func handle(_ error: Error) -> String? {
        if let api = error as? APIError, api == .signedOut {
            phase = .signedOut
            return nil
        }
        return error.localizedDescription
    }

    func signOut() async {
        let _: OK? = try? await api.post("api/auth/logout")
        api.clearCookies()
        phase = .signedOut
    }

    var user: PearlUser? {
        if case .signedIn(let user) = phase { return user }
        return nil
    }
}
