import SwiftUI

/// The bar along the bottom, as Pearl on the web draws it on a phone: line
/// icons over small labels, the open one in Pearl's pink, a hairline on top.
struct PearlTabBar: View {
    @Binding var selection: MainTabs.Tab
    var badges: [MainTabs.Tab: Int] = [:]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(MainTabs.Tab.allCases, id: \.self) { tab in
                Button { selection = tab } label: {
                    VStack(spacing: 3) {
                        TabIcon(tab: tab)
                            .stroke(style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
                            .frame(width: 21, height: 21)
                            .overlay(alignment: .topTrailing) { badge(for: tab) }
                        Text(tab.label)
                            .font(Pearl.text(.caption2, .semibold))
                    }
                    .foregroundColor(selection == tab ? Pearl.action : Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(tab.label)
                .accessibilityAddTraits(selection == tab ? .isSelected : [])
            }
        }
        .padding(.horizontal, 4)
        .padding(.top, 6)
        .padding(.bottom, 2)
        .background(Pearl.bar.opacity(0.94).ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Pearl.border).frame(height: 1) }
    }

    @ViewBuilder private func badge(for tab: MainTabs.Tab) -> some View {
        if let count = badges[tab], count > 0 {
            Text("\(count)")
                .font(Pearl.text(.caption2, .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 5)
                .frame(minWidth: 16, minHeight: 16)
                .background(Pearl.rose)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .offset(x: 12, y: -6)
                .accessibilityLabel("\(count) need a look")
        }
    }
}

/// The web's tab icons (src/nav.js), drawn on its 24-point grid.
struct TabIcon: Shape {
    let tab: MainTabs.Tab

    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 24
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + x * s, y: rect.minY + y * s)
        }
        var path = Path()
        switch tab {
        case .home:
            // M3 10.5 12 3l9 7.5M5 9v11h5v-6h4v6h5V9
            path.move(to: p(3, 10.5)); path.addLine(to: p(12, 3)); path.addLine(to: p(21, 10.5))
            path.move(to: p(5, 9))
            for (x, y) in [(5, 20), (10, 20), (10, 14), (14, 14), (14, 20), (19, 20), (19, 9)] as [(CGFloat, CGFloat)] {
                path.addLine(to: p(x, y))
            }
        case .cashFlow:
            // Two waves: M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0, and the same at 16.
            for y in [8, 16] as [CGFloat] {
                path.move(to: p(3, y))
                path.addCurve(to: p(9, y), control1: p(5, y - 2), control2: p(7, y - 2))
                path.addCurve(to: p(15, y), control1: p(11, y + 2), control2: p(13, y + 2))
                path.addCurve(to: p(21, y), control1: p(17, y - 2), control2: p(19, y - 2))
            }
        case .profile:
            // M20 21a8 8 0 0 0-16 0 and a circle of 5 at (12, 8).
            path.addArc(center: p(12, 21), radius: 8 * s,
                        startAngle: .degrees(0), endAngle: .degrees(180), clockwise: true)
            path.addEllipse(in: CGRect(origin: p(7, 3), size: CGSize(width: 10 * s, height: 10 * s)))
        }
        return path
    }
}
