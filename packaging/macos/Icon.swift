import AppKit
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(calibratedRed: 0.09, green: 0.20, blue: 0.23, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 32, y: 32, width: 960, height: 960), xRadius: 220, yRadius: 220).fill()
NSColor(calibratedRed: 0.33, green: 0.78, blue: 0.74, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 226, y: 250, width: 572, height: 556), xRadius: 258, yRadius: 258).fill()
for x in [235, 390, 545, 700] { NSBezierPath(roundedRect: NSRect(x: x, y: 180, width: 95, height: 220), xRadius: 47, yRadius: 47).fill() }
NSColor(calibratedRed: 0.09, green: 0.20, blue: 0.23, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 296, y: 415, width: 432, height: 246), xRadius: 123, yRadius: 123).fill()
NSColor.white.setFill()
for x in [375, 558] { NSBezierPath(ovalIn: NSRect(x: x, y: 478, width: 80, height: 120)).fill() }
NSColor(calibratedRed: 0.09, green: 0.20, blue: 0.23, alpha: 1).setFill()
for x in [402, 585] { NSBezierPath(ovalIn: NSRect(x: x, y: 484, width: 36, height: 50)).fill() }
image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
