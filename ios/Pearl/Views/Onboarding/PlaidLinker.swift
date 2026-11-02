import LinkKit
import SwiftUI
import UIKit

/// Plaid Link, as O-07 to O-07e show it: Plaid draws the bank picker, the
/// bank's own sign-in and "choose accounts". Pearl gets a public token back,
/// which the server exchanges (O-08).
@MainActor
final class PlaidLinker: ObservableObject {
    /// What linking gave back: the bank, and the accounts she chose to share.
    struct Linked: Hashable {
        let publicToken: String
        let institution: String
        let accounts: [Account]

        struct Account: Hashable {
            let name: String
            let mask: String
        }
    }

    enum Outcome {
        case linked(Linked)
        /// She closed Plaid: not an error (THL-119), back to where she was.
        case cancelled
        case failed(String)
        case notSupported(String)
    }

    private var handler: Handler?

    func open(api: APIClient) async throws -> Outcome {
        let token: LinkToken = try await api.post("api/plaid/link-token")
        return try await withCheckedThrowingContinuation { continuation in
            var finished = false
            // The handler is kept until the next open replaces it.
            func finish(_ outcome: Outcome) {
                guard !finished else { return }
                finished = true
                continuation.resume(returning: outcome)
            }
            var config = LinkTokenConfiguration(token: token.linkToken) { success in
                let accounts = success.metadata.accounts.map {
                    Linked.Account(name: $0.name, mask: $0.mask ?? "")
                }
                finish(.linked(Linked(publicToken: success.publicToken,
                                      institution: success.metadata.institution.name,
                                      accounts: accounts)))
            }
            config.onExit = { exit in
                let bank = exit.metadata.institution?.name ?? "your bank"
                guard let error = exit.error else {
                    finish(.cancelled)
                    return
                }
                let code = String(describing: error.errorCode).lowercased()
                if code.contains("notsupported") || code.contains("not_supported") || code.contains("nosupported") {
                    finish(.notSupported(bank))
                } else {
                    finish(.failed(bank))
                }
            }
            switch Plaid.create(config) {
            case .success(let handler):
                self.handler = handler
                guard let top = Self.topController() else {
                    finished = true
                    continuation.resume(throwing: APIError.message("Plaid couldn’t open. Try again."))
                    return
                }
                handler.open(presentUsing: .viewController(top))
            case .failure(let error):
                finished = true
                continuation.resume(throwing: APIError.message("Plaid couldn’t open: \(error.localizedDescription)"))
            }
        }
    }

    private static func topController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive } ?? UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }.first
        var top = scene?.windows.first { $0.isKeyWindow }?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
}
