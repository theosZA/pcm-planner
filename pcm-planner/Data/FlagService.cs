using Nager.Country;

namespace Data;

public sealed record FlagInfo(string Alpha2Code, string CountryName, string FlagSvgUrl, string FlagAltText);

public class FlagService
{
  private const string FlagCdnBaseUrl = "https://flagcdn.com";

  private readonly Dictionary<string, ICountryInfo> _countriesByAlpha3;

  private static readonly Dictionary<string, FlagInfo> ManualOverrides = new()
  {
    // PCM uses some non-standard codes.
    ["CHI"] = new FlagInfo("ZH", "China", $"{FlagCdnBaseUrl}/cn.svg", "Flag of China"),
    ["CRO"] = new FlagInfo("HR", "Croatia", $"{FlagCdnBaseUrl}/hr.svg", "Flag of Croatia"),
    ["KOS"] = new FlagInfo("XK", "Kosovo", $"{FlagCdnBaseUrl}/xk.svg", "Flag of Kosovo"),
    ["MAS"] = new FlagInfo("MY", "Malaysia", $"{FlagCdnBaseUrl}/my.svg", "Flag of Malaysia"),
    ["ROM"] = new FlagInfo("RO", "Romania", $"{FlagCdnBaseUrl}/ro.svg", "Flag of Romania"),
    ["SLO"] = new FlagInfo("SI", "Slovenia", $"{FlagCdnBaseUrl}/si.svg", "Flag of Slovenia"),

    // Add more overrides here if needed in the future.
  };

  public FlagService()
  {
    var provider = new CountryProvider();

    _countriesByAlpha3 = provider
        .GetCountries()
        .ToDictionary(
            c => c.Alpha3Code.ToString().ToUpperInvariant(),
            c => c
        );
  }

  public FlagInfo? GetFlagInfo(string? alpha3Code)
  {
    if (string.IsNullOrWhiteSpace(alpha3Code))
      return null;
    var key = alpha3Code.Trim().ToUpperInvariant();
    // Check for manual override first.
    if (ManualOverrides.TryGetValue(key, out var overrideInfo))
      return overrideInfo;
    // Fall back to standard country info.
    if (!_countriesByAlpha3.TryGetValue(key, out var country) || country is null)
      return null;
    var alpha2 = country.Alpha2Code.ToString().ToLowerInvariant();
    var flagUrl = $"{FlagCdnBaseUrl}/{alpha2}.svg";
    var altText = $"Flag of {country.CommonName}";
    return new FlagInfo(country.Alpha2Code.ToString(), country.CommonName, flagUrl, altText);
  }
}