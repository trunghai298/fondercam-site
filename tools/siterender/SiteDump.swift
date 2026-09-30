#if os(macOS)
import Foundation
import FilmKit

/// What the fondercam.online build needs from the shipped catalogue, exposed the same
/// way `SampleCatalogue` is: `Looks` is internal to this module, so the site's render
/// tool reads the catalogue through here rather than through a copied table.
public enum SiteDump {
    public struct Entry: Codable {
        public let id: String
        public let name: String
        public let free: Bool
        public let filmCharacter: String?
        public let grainStrength: Int   // whole percent, as the share format writes it
        public let grainLarge: Bool
    }

    public static var entries: [Entry] {
        Looks.all.map { look in
            Entry(id: look.id, name: look.name, free: look.free,
                  filmCharacter: look.recipe.filmColor?.character,
                  grainStrength: Int((look.recipe.grain.strength * 100).rounded()),
                  grainLarge: look.recipe.grain.size >= 2)
        }
    }

    /// The Films library's palette line, derived exactly as the app derives it
    /// (`CharacterPalette` in App/Sources/Recipes/CharacterSwatch.swift): six memory
    /// colours run through the character's own maths, encoded to sRGB.
    public static let paletteInputs = [OKLCh(L: 0.35, C: 0.005, h: 260),
                                       OKLCh(L: 0.55, C: 0.12, h: 25),
                                       OKLCh(L: 0.72, C: 0.08, h: 60),
                                       OKLCh(L: 0.55, C: 0.10, h: 140),
                                       OKLCh(L: 0.68, C: 0.10, h: 250),
                                       OKLCh(L: 0.88, C: 0.005, h: 90)]

    public static func palette(for character: FilmCharacter) -> [String] {
        let math = FilmColorMath(character: character)
        return paletteInputs.map { input in
            let c = math.apply(OKLabConvert.toLinear(OKLabConvert.toLab(input)))
            let hex = { (v: Double) -> String in String(format: "%02x", Int((FilmColorBake.encode(v) * 255).rounded())) }
            return "#" + hex(c.r) + hex(c.g) + hex(c.b)
        }
    }

    /// The anatomy pairs, taken from one reference recipe in the shipped catalogue: the
    /// neutral decode, the recipe's film alone, and then the film with exactly one of the
    /// recipe's own settings applied — one card per setting, everything else left neutral,
    /// so each render is that setting's isolated effect, at its authored value, through
    /// the real graph. A setting the recipe leaves neutral (only exposure, for 1998 Neg)
    /// gets a demonstrative value instead, and the page's card label says which is which.
    public static func variantRecipes(reference id: String) -> [(slug: String, recipe: Recipe)]? {
        guard let ref = Looks.all.first(where: { $0.id == id })?.recipe else { return nil }
        func base(_ name: String, withFilm: Bool = true) -> Recipe {
            var r = Recipe.neutral(simulation: SimulationID("neutral"), name: name)
            if withFilm { r.filmColor = ref.filmColor }
            r.strength = 1
            return r
        }
        var out: [(String, Recipe)] = []
        out.append(("neutral", base("neutral", withFilm: false)))
        out.append(("film", base("film")))

        var wb = base("wb"); wb.whiteBalance = ref.whiteBalance; out.append(("wb", wb))
        var ht = base("highlight"); ht.highlightTone = ref.highlightTone; out.append(("highlight", ht))
        var st = base("shadow"); st.shadowTone = ref.shadowTone; out.append(("shadow", st))
        var co = base("colour"); co.color = ref.color; out.append(("colour", co))
        var cc = base("chrome"); cc.colorChrome = ref.colorChrome; cc.colorChromeBlue = ref.colorChromeBlue; out.append(("chrome", cc))
        var dr = base("dr"); dr.dynamicRange = ref.dynamicRange; out.append(("dr", dr))
        var ev = base("exposure")
        ev.exposureCompensation = ref.exposureCompensation != 0 ? ref.exposureCompensation : -2.0 / 3.0
        out.append(("exposure", ev))
        var cl = base("clarity"); cl.clarity = ref.clarity; out.append(("clarity", cl))
        var sh = base("sharpness"); sh.sharpness = ref.sharpness; out.append(("sharpness", sh))
        var gr = base("grain"); gr.grain = ref.grain; out.append(("grain", gr))
        var ha = base("halation"); ha.halation = ref.halation; out.append(("halation", ha))
        var vi = base("vignette"); vi.vignette = ref.vignette; out.append(("vignette", vi))
        return out
    }
}
#endif
