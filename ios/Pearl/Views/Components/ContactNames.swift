import Contacts
import SwiftUI
import UIKit

/// Names from her iPhone's contacts, for the pickers that ask who someone
/// is: Add people (AM-08p1), and Who sent this? (product owner,
/// 2026-11-20: "I should still be able to search my contacts, or add a
/// name"). Names only, asked for the first time a picker opens, never sent
/// anywhere; a contact with no first or last name falls back to its
/// nickname, then company.
@MainActor
final class ContactNames: ObservableObject {
    enum State { case asking, on, off }

    @Published private(set) var names: [String] = []
    @Published private(set) var state: State = .asking
    /// iOS 18 "limited access": Pearl only sees the contacts she chose.
    @Published private(set) var limited = false

    /// Browsing shows the first 60; searching looks through all of them.
    static let browseCap = 60

    func load() async {
        let store = CNContactStore()
        if CNContactStore.authorizationStatus(for: .contacts) == .notDetermined {
            _ = try? await store.requestAccess(for: .contacts)
        }
        let status = CNContactStore.authorizationStatus(for: .contacts)
        guard status != .denied && status != .restricted && status != .notDetermined else {
            state = .off
            return
        }
        if #available(iOS 18.0, *) { limited = status == .limited }
        let found: [String] = await Task.detached {
            let keys = [CNContactGivenNameKey, CNContactFamilyNameKey,
                        CNContactNicknameKey, CNContactOrganizationNameKey] as [CNKeyDescriptor]
            var out: [String] = []
            let request = CNContactFetchRequest(keysToFetch: keys)
            request.sortOrder = .givenName
            try? store.enumerateContacts(with: request) { c, _ in
                var name = "\(c.givenName) \(c.familyName)".trimmingCharacters(in: .whitespaces)
                if name.isEmpty { name = c.nickname.trimmingCharacters(in: .whitespaces) }
                if name.isEmpty { name = c.organizationName.trimmingCharacters(in: .whitespaces) }
                if !name.isEmpty { out.append(name) }
            }
            return out
        }.value
        var seen = Set<String>()
        names = found.filter { seen.insert($0.lowercased()).inserted }
            .sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
        state = .on
    }

    /// The contacts matching `query` (all of them when she searches, the
    /// first 60 when she browses), leaving out anyone already listed.
    func matches(_ query: String, excluding listed: [String]) -> [String] {
        guard state == .on else { return [] }
        let q = query.trimmingCharacters(in: .whitespaces)
        let all = names.filter { c in
            (q.isEmpty || c.localizedCaseInsensitiveContains(q))
                && !listed.contains { $0.caseInsensitiveCompare(c) == .orderedSame }
        }
        return q.isEmpty ? Array(all.prefix(Self.browseCap)) : all
    }

    /// Whether `name` is exactly one she already has (so "Add" isn't offered).
    func has(_ name: String) -> Bool {
        names.contains { $0.caseInsensitiveCompare(name) == .orderedSame }
    }

    /// iOS Settings › Pearl, never the web (JOINT-A note 1110:6476).
    static func openSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }
}

/// "Contacts are off for Pearl. Turn on": the one quiet line under a list
/// when Pearl may not read her contacts (AM-08p2).
struct ContactsOffLine: View {
    var body: some View {
        HStack(spacing: 4) {
            Text("Contacts are off for Pearl.").foregroundColor(Pearl.muted)
            Button("Turn on", action: ContactNames.openSettings).foregroundColor(Pearl.link).buttonStyle(.plain)
            Spacer(minLength: 0)
        }
        .font(Nacre.footnote)
        .frame(minHeight: 32)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Turn on in Settings", ContactNames.openSettings)
    }
}

/// "+ Add “Maya” as a new name": the typed name as one row to pick, when
/// nobody listed matches it exactly.
struct AddTypedNameRow: View {
    let name: String
    let picked: Bool
    let pick: () -> Void

    var body: some View {
        Button(action: pick) {
            HStack(spacing: 12) {
                Image(systemName: "plus").font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Pearl.action)
                    .frame(width: 28, height: 28).background(Circle().fill(APlus.actionWash))
                Text("Add “\(name)” as a new name").font(Nacre.body).foregroundColor(Pearl.action)
                Spacer(minLength: 8)
                if picked {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(picked ? .isSelected : [])
        .accessibilityIdentifier("picker-add-typed")
    }
}
