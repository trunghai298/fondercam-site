#if os(macOS)
import CoreGraphics
import FilmKit
import FilmSample
import Foundation

// usage: siterender --frame <no-look jpeg> --luts <dir> --characters <dir> --out <dir>
//                   [--reference neg1998] [--longEdge 1600] [--longEdges 700,1400]
// Writes <out>/anatomy/<slug>.jpg for every SiteDump variant, <out>/catalogue.json
// (the shipped looks) and <out>/palettes.json (every character's six swatches).

var flags: [String: String] = [:]
var args = Array(CommandLine.arguments.dropFirst())
var i = 0
while i + 1 < args.count { flags[args[i]] = args[i + 1]; i += 2 }
guard let framePath = flags["--frame"], let lutPath = flags["--luts"],
      let charPath = flags["--characters"], let outPath = flags["--out"] else {
    FileHandle.standardError.write(Data("usage: siterender --frame f --luts d --characters d --out d\n".utf8))
    exit(2)
}
let reference = flags["--reference"] ?? "neg1998"
let longEdge = CGFloat(Double(flags["--longEdge"] ?? "1600")!)

let out = URL(fileURLWithPath: outPath)
try! FileManager.default.createDirectory(at: out.appendingPathComponent("anatomy"), withIntermediateDirectories: true)

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
try! encoder.encode(SiteDump.entries).write(to: out.appendingPathComponent("catalogue.json"))

struct PaletteFile: Codable { let palettes: [String: [String]]; let names: [String: String] }
let characters = CharacterStore(directory: URL(fileURLWithPath: charPath))
var palettes: [String: [String]] = [:]
var names: [String: String] = [:]
for c in characters.all { palettes[c.id] = SiteDump.palette(for: c); names[c.id] = c.name }
try! encoder.encode(PaletteFile(palettes: palettes, names: names)).write(to: out.appendingPathComponent("palettes.json"))

let renderer = SampleRenderer(lutDirectory: URL(fileURLWithPath: lutPath),
                              characterDirectory: URL(fileURLWithPath: charPath))
let frame = try! SampleRenderer.loadFrame(at: URL(fileURLWithPath: framePath))
guard let variants = SiteDump.variantRecipes(reference: reference) else {
    FileHandle.standardError.write(Data("no look called '\(reference)'\n".utf8)); exit(1)
}
// One render per output size, not one render downscaled: grain, halation and clarity
// are sized by the graph for the resolution they are rendered at, exactly as on the
// phone, so each srcset variant carries correctly-scaled effects.
let anatomyEdges = (flags["--longEdges"] ?? String(Int(longEdge)))
    .split(separator: ",").map { CGFloat(Double($0)!) }
for (slug, recipe) in variants {
    for edge in anatomyEdges {
        let image = try! renderer.render(frame: frame, recipe: recipe, longEdge: edge)
        let dest = out.appendingPathComponent("anatomy/\(slug)-\(Int(edge)).jpg")
        try! renderer.writeJPEG(image, to: dest, quality: 0.95)
        print("\(slug)  \(image.width)x\(image.height)")
    }
}

// Whole shipped recipes over the same frame, at the sample pipeline's own strength —
// stand-ins for bundled samples the site cannot show (the ones with a face in them).
if let list = flags["--looks"] {
    try! FileManager.default.createDirectory(at: out.appendingPathComponent("looks"), withIntermediateDirectories: true)
    for id in list.split(separator: ",").map(String.init) {
        guard let recipe = SampleCatalogue.recipe(id, strength: 0.8) else {
            FileHandle.standardError.write(Data("no look called '\(id)'\n".utf8)); exit(1)
        }
        let image = try! renderer.render(frame: frame, recipe: recipe, longEdge: longEdge)
        try! renderer.writeJPEG(image, to: out.appendingPathComponent("looks/\(id).jpg"), quality: 0.95)
        print("look \(id)  \(image.width)x\(image.height)")
    }
}
print("done")
#endif
