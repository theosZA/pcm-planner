namespace pcm_planner.Data;

public static class CalendarHelpers
{
  public static string FormatDates(DateOnly start, DateOnly end)
  {
    if (start == end)
      return start.ToString("d MMM yyyy");
    return $"{start:d MMM yyyy} – {end:d MMM yyyy}";
  }

  public static string CalendarTooltip(RiderAssignedRace race)
  {
    var tooltipText = $"{RaceLevel(race)} | {race.Name} | {FormatDates(race.StartDate, race.EndDate)}";
    if (race.StageCount > 1)
      tooltipText += $" | {race.StageCount} stages";
    return tooltipText;
  }

  public static string RaceLabel(RiderAssignedRace race) => race.Abbreviation;

  public static string RaceColour(RiderAssignedRace race) => race.Class switch
  {
    "CWTGTFrance" => "#EED712",
    "CWTGTAutres" => race.Name.ToLowerInvariant().Contains("giro") ? "#F095BD" : "#D2722A",
    _ => '#' + race.CalendarColor
  };

  public static string TextColourForBackground(string hexColour)
  {
    var text = hexColour.TrimStart('#');
    if (text.Length < 6) return "#111";
    var r = Convert.ToInt32(text[..2], 16);
    var g = Convert.ToInt32(text.Substring(2, 2), 16);
    var b = Convert.ToInt32(text.Substring(4, 2), 16);
    var brightness = (r * 299 + g * 587 + b * 114) / 1000;
    return brightness >= 150 ? "#111" : "#fff";
  }

  public static string RaceLevel(RiderAssignedRace race) => race.Class switch
  {
    "WorldChampionship" => "World Championship",
    "WorldChampionshipITT" => "World Championship ITT",
    "EuropeanChampionship" => "European Championship",
    "EuropeanChampionshipITT" => "European Championship ITT",
    "NationalChampionship" => "National Championship",
    "NationalChampionshipITT" => "National Championship ITT",
    "CWTGTFrance" => "Grand Tour",
    "CWTGTAutres" => "Grand Tour",
    "CWTMajeures" => "World Tour Monument",
    "CWTAutresClasA" => "World Tour Classic A",
    "CWTAutresClasB" => "World Tour Classic B",
    "CWTAutresClasC" => "World Tour Classic C",
    "CWTAutresToursA" => "World Tour A",
    "CWTAutresToursB" => "World Tour B",
    "CWTAutresToursC" => "World Tour C",
    "Cont2HC" => "2.Pro",
    "Cont1HC" => "1.Pro",
    "Cont12" => "1.2",
    "Cont11" => "1.1",
    "Cont22" => "2.2",
    "Cont21" => "2.1",
    "U23_2NCup" => "U23 Nations' Cup",
    "Cont12U" => "1.2 U23",
    "Cont22U" => "2.2 U23",
    _ => race.Class
  };
}
