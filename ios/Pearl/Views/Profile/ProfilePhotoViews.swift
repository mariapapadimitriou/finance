import AVFoundation
import SwiftUI
import UIKit

// A+ profile photo (REDESIGN-03, REDESIGN-11 G5-Photo, REDESIGN-16;
// AP-Profile, AP-PhotoSheet, AP-Crop). Add photo / Change photo under the
// avatar opens a Pearl sheet: Choose photo, Take photo, Remove photo (only
// when one is set), Cancel. Then Move and scale, every time, with Use photo
// and Cancel. Saving fills a ring round the avatar; a failure says so in the
// ink toast with Try again. The photo stays on this iPhone (ProfilePhotoStore).

/// What she picked on the photo sheet; it runs once the sheet has gone.
enum PhotoChoice {
    case choose, take, remove
}

/// AP-PhotoSheet: the avatar, "Profile photo", the options in one card, Cancel.
struct PhotoOptionsSheet: View {
    let initials: String
    let photo: UIImage?
    let pick: (PhotoChoice) -> Void
    let onClose: () -> Void

    /// Take photo only on an iPhone with a camera (REDESIGN-16).
    private var hasCamera: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }

    var body: some View {
        PearlSheet {
            VStack(spacing: 10) {
                ProfileAvatar(initials: initials, photo: photo, size: 64,
                              font: .custom("Figtree-SemiBold", size: 20, relativeTo: .title3))
                Text("Profile photo").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity)
            PearlOptionCard {
                row("photo", "Choose photo", .choose)
                if hasCamera {
                    PearlDivider()
                    row("camera", "Take photo", .take)
                }
                if photo != nil {
                    PearlDivider()
                    // Red only for the destructive entry (REDESIGN-12, decision 6).
                    row("trash", "Remove photo", .remove, tone: Pearl.danger)
                }
            }
        } footer: {
            Button("Cancel", action: onClose)
                .buttonStyle(PearlSecondaryButtonStyle())
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
        }
    }

    private func row(_ symbol: String, _ title: String, _ choice: PhotoChoice,
                     tone: Color = Pearl.ink) -> some View {
        Button { pick(choice) } label: {
            HStack(spacing: 12) {
                PearlBubble(symbol: symbol, size: 36)
                Text(title).font(Nacre.body).foregroundColor(tone)
                Spacer(minLength: 8)
            }
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("photo-\(choice)")
    }
}

/// AP-Crop: "Move and scale". The photo fills a square; she drags and
/// pinches it under a circle; Use photo keeps what's inside the circle.
struct PhotoCropView: View {
    let image: UIImage
    let use: (UIImage) -> Void
    let cancel: () -> Void

    @State private var zoom: CGFloat = 1
    @State private var lastZoom: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    var body: some View {
        GeometryReader { geo in
            let side = max(1, geo.size.width - 32)
            let hole = side * 0.84
            VStack(spacing: 0) {
                Text("Move and scale").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .frame(height: 44).padding(.top, 6)
                Spacer(minLength: 24)
                frame(side: side, hole: hole)
                Spacer(minLength: 24)
                VStack(spacing: 4) {
                    Button("Use photo") { use(crop(side: side, hole: hole)) }
                        .buttonStyle(PearlPrimaryButtonStyle())
                        .accessibilityIdentifier("photo-use")
                    Button("Cancel", action: cancel)
                        .font(Nacre.textButton).foregroundColor(Pearl.link)
                        .frame(minHeight: 44)
                        .buttonStyle(.plain)
                }
                .padding(.horizontal, 16).padding(.bottom, 8)
            }
            .frame(maxWidth: .infinity)
        }
        .nacreScreen()
    }

    private func frame(side: CGFloat, hole: CGFloat) -> some View {
        let shown = displayed(side: side)
        return ZStack {
            Image(uiImage: image).resizable()
                .frame(width: shown.width, height: shown.height)
                .offset(offset)
            // Dim outside the circle; the circle shows the photo as it will be.
            Rectangle().fill(Color.black.opacity(0.35))
                .mask(
                    Rectangle().overlay(Circle().frame(width: hole, height: hole).blendMode(.destinationOut))
                        .compositingGroup()
                )
                .allowsHitTesting(false)
            Circle().strokeBorder(Color.white, lineWidth: 2).frame(width: hole, height: hole)
                .allowsHitTesting(false)
        }
        .frame(width: side, height: side)
        .clipShape(RoundedRectangle(cornerRadius: Pearl.radiusTile, style: .continuous))
        .contentShape(Rectangle())
        .gesture(
            SimultaneousGesture(
                DragGesture()
                    .onChanged { v in
                        offset = clamp(CGSize(width: lastOffset.width + v.translation.width,
                                              height: lastOffset.height + v.translation.height),
                                       side: side, hole: hole)
                    }
                    .onEnded { _ in lastOffset = offset },
                MagnificationGesture()
                    .onChanged { m in
                        zoom = min(5, max(1, lastZoom * m))
                        offset = clamp(offset, side: side, hole: hole)
                    }
                    .onEnded { _ in
                        lastZoom = zoom
                        lastOffset = offset
                    }
            )
        )
        .accessibilityElement()
        .accessibilityLabel("Your photo, in the circle")
        .accessibilityHint("Drag to move it, pinch to scale it.")
        .accessibilityAdjustableAction { direction in
            // VoiceOver: swipe up and down to scale.
            zoom = min(5, max(1, zoom + (direction == .increment ? 0.25 : -0.25)))
            lastZoom = zoom
            offset = clamp(offset, side: side, hole: hole)
            lastOffset = offset
        }
    }

    /// The photo's size on screen: filling the square, times her zoom.
    private func displayed(side: CGFloat) -> CGSize {
        let w = max(1, image.size.width), h = max(1, image.size.height)
        let fill = side / min(w, h)
        return CGSize(width: w * fill * zoom, height: h * fill * zoom)
    }

    /// The circle always stays covered by the photo.
    private func clamp(_ o: CGSize, side: CGFloat, hole: CGFloat) -> CGSize {
        let shown = displayed(side: side)
        let dx = max(0, (shown.width - hole) / 2), dy = max(0, (shown.height - hole) / 2)
        return CGSize(width: min(dx, max(-dx, o.width)), height: min(dy, max(-dy, o.height)))
    }

    /// What's inside the circle, as a 512 × 512 square (the avatar clips it round).
    private func crop(side: CGFloat, hole: CGFloat) -> UIImage {
        let shown = displayed(side: side)
        let out: CGFloat = 512
        let k = out / hole
        // Where the photo's top-left corner sits, relative to the circle's.
        let x = (hole - shown.width) / 2 + offset.width
        let y = (hole - shown.height) / 2 + offset.height
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: CGSize(width: out, height: out), format: format).image { _ in
            image.draw(in: CGRect(x: x * k, y: y * k, width: shown.width * k, height: shown.height * k))
        }
    }
}

/// Take photo: the system camera (the only camera UI there is), front camera first.
struct CameraPicker: UIViewControllerRepresentable {
    let done: (UIImage?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        if UIImagePickerController.isCameraDeviceAvailable(.front) { picker.cameraDevice = .front }
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(done: done) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let done: (UIImage?) -> Void
        init(done: @escaping (UIImage?) -> Void) { self.done = done }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            done(info[.originalImage] as? UIImage)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { done(nil) }
    }
}

enum CameraAccess {
    /// May Pearl use the camera? Asks the first time.
    static func allowed() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
        default: return false
        }
    }
}

/// G5-Photo: the avatar while saving, a ring filling round it.
struct SavingRing: View {
    let size: CGFloat
    @State private var fill: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Circle()
            .trim(from: 0, to: fill)
            .stroke(Pearl.action, style: StrokeStyle(lineWidth: 3, lineCap: .round))
            .rotationEffect(.degrees(-90))
            .frame(width: size + 4, height: size + 4)
            .onAppear {
                if reduceMotion { fill = 1 } else { withAnimation(.easeInOut(duration: 0.6)) { fill = 1 } }
            }
            .accessibilityHidden(true)
    }
}
