import AppKit

// Render the same vector used in the sidebar, without fonts or third-party image dependencies.
final class Mark: NSObject, XMLParserDelegate {
    var stroke = ""
    var strokeWidth: CGFloat = 0
    var commands = ""

    func parser(_ parser: XMLParser, didStartElement name: String, namespaceURI: String?,
                qualifiedName: String?, attributes: [String: String]) {
        if name == "svg" || name == "path" {
            stroke = attributes["stroke"] ?? stroke
            if let width = attributes["stroke-width"], let value = Double(width) { strokeWidth = CGFloat(value) }
        }
        if name == "path" { commands += " " + (attributes["d"] ?? "") }
    }
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

func color(_ hex: String) -> CGColor {
    guard hex.hasPrefix("#"), hex.count == 7, let value = UInt32(hex.dropFirst(), radix: 16) else {
        fail("Icon source must contain a six-digit stroke color.")
    }
    return CGColor(colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!, components: [
        CGFloat((value >> 16) & 255) / 255,
        CGFloat((value >> 8) & 255) / 255,
        CGFloat(value & 255) / 255, 1,
    ])!
}

func vector(_ commands: String) -> CGPath {
    let pattern = try! NSRegularExpression(pattern: "[A-Za-z]|[-+]?(?:[0-9]*\\.)?[0-9]+")
    let source = commands as NSString
    let tokens = pattern.matches(in: commands, range: NSRange(location: 0, length: source.length))
        .map { source.substring(with: $0.range) }
    let path = CGMutablePath()
    var index = 0
    func number() -> CGFloat {
        guard index < tokens.count, let value = Double(tokens[index]) else { fail("Invalid icon path.") }
        index += 1
        return CGFloat(value)
    }
    func point() -> CGPoint { CGPoint(x: number(), y: number()) }
    while index < tokens.count {
        let command = tokens[index]
        index += 1
        switch command {
        case "M": path.move(to: point())
        case "L": path.addLine(to: point())
        case "C":
            let first = point(), second = point(), end = point()
            path.addCurve(to: end, control1: first, control2: second)
        case "Z": path.closeSubpath()
        default: fail("Unsupported icon path command: \(command). Use explicit M, L, C, Z commands.")
        }
    }
    return path
}

guard CommandLine.arguments.count == 3 else { fail("Usage: BuildIcon source.svg output.iconset") }
let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
let mark = Mark()
guard let parser = XMLParser(contentsOf: sourceURL) else { fail("Unable to read the logo SVG.") }
parser.delegate = mark
guard parser.parse(), !mark.commands.isEmpty, mark.strokeWidth > 0 else { fail("Invalid logo SVG.") }
let path = vector(mark.commands)
let bounds = path.boundingBoxOfPath
guard bounds.width > 0, bounds.height > 0 else { fail("Empty logo vector.") }
try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let sizes = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)]
for (logicalSize, factor) in sizes {
    let pixels = logicalSize * factor
    let size = CGFloat(pixels)
    guard let context = CGContext(data: nil, width: pixels, height: pixels, bitsPerComponent: 8,
                                  bytesPerRow: 0, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        fail("Unable to create icon bitmap.")
    }
    context.setAllowsAntialiasing(true)
    context.setShouldAntialias(true)
    let inset = size / 16
    let tile = CGRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
    context.addPath(CGPath(roundedRect: tile, cornerWidth: size * 0.19, cornerHeight: size * 0.19, transform: nil))
    context.setFillColor(color("#111314"))
    context.fillPath()
    let scale = size * 0.64 / (bounds.width + mark.strokeWidth)
    context.translateBy(x: size / 2, y: size / 2)
    context.scaleBy(x: scale, y: -scale)
    context.translateBy(x: -bounds.midX, y: -bounds.midY)
    context.setStrokeColor(color(mark.stroke))
    context.setLineWidth(mark.strokeWidth)
    context.setLineCap(.round)
    context.setLineJoin(.round)
    context.addPath(path)
    context.strokePath()
    guard let image = context.makeImage(),
          let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
        fail("Unable to encode icon bitmap.")
    }
    let suffix = factor == 2 ? "@2x" : ""
    try png.write(to: outputURL.appendingPathComponent("icon_\(logicalSize)x\(logicalSize)\(suffix).png"))
}
