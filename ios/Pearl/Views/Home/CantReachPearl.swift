import SwiftUI
import UIKit

// G6-Offline (REDESIGN-13, -14: new function, approved). At launch, when the
// server can't be reached: Can't reach Pearl, with Try again. Over Home, when
// a refresh can't reach it but Home already has what it showed: the
// champagne banner "Offline · showing Pearl from 9:12".

/// Can't reach Pearl: the wifi-slash in a 120 pt `action-wash` circle, the
/// title in Fraunces 34, one line in `muted` 17, Try again at the bottom.
struct CantReachPearlView: View {
    let retry: () async -> Void
    @State private var trying = false

    var body: some View {
        VStack(spacing: 0) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 44, weight: .regular))
                .foregroundColor(Pearl.action)
                .frame(width: 120, height: 120)
                .background(Circle().fill(APlus.actionWash))
                .padding(.top, 150)
                .accessibilityHidden(true)
            Text("Can\u{2019}t reach Pearl").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.top, 32)
                .accessibilityAddTraits(.isHeader)
            Text("Check your connection. Your money is safe; Pearl only reads it.")
                .font(Nacre.body).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 20).padding(.top, 8)
            Spacer(minLength: 24)
            Button("Try again") {
                Task {
                    trying = true
                    await retry()
                    trying = false
                }
            }
            .buttonStyle(NacreButtonStyle(busy: trying))
            .disabled(trying)
            .accessibilityIdentifier("offline-try-again")
        }
        .padding(.horizontal, Pearl.gutter)
        .padding(.bottom, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .nacreScreen()
    }
}

/// `.banner` on `card`: the caution icon and "Offline · showing Pearl from 9:12".
struct OfflineBanner: View {
    let since: Date

    var body: some View {
        HStack(spacing: 12) {
            APIcon(symbol: "exclamationmark.triangle", tone: .warn)
            Text("Offline \u{00B7} showing Pearl from \(since.formatted(date: .omitted, time: .shortened))")
                .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(APlus.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .onAppear {
            UIAccessibility.post(notification: .announcement, argument: "Offline. Showing Pearl from earlier.")
        }
    }
}
