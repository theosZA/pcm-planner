using Microsoft.Data.Sqlite;

namespace pcm_planner.Data;

public record RiderRaceDays(int Id, string DisplayName, int RaceDays);

public record RiderDetail(
    int Id,
    string DisplayName,
    int? Age,
    int? Flat, int? Hill, int? MediumMountain, int? Mountain,
    int? TimeTrial, int? Prologue, int? Cobble,
    int? Sprint, int? Acceleration,
    int? Stamina, int? Resistance, int? Recovery, int? Baroudeur);

public record RiderAssignedRace(
    int RaceId,
    string Name,
    string Abbreviation,
    DateOnly StartDate,
    DateOnly EndDate,
    int StageCount,
    string Class,
    string CalendarColor);

public record RaceStage(int StageNumber, string? Relief, string? StageType);

public record RaceRider(int Id, string DisplayName);

public record RaceDetail(
    int Id,
    string Name,
    DateOnly StartDate,
    DateOnly EndDate,
    List<RaceStage> Stages,
    List<RaceRider> Riders,
    int? StageValue,
    string? SquadProfile);

public record SeasonSummary(int Season, int RaceCount, int RiderCount, double AvgRaceDays);

public record RiderCalendarEntry(int RiderId, string DisplayName, List<RiderAssignedRace> Races);

public class RosterService
{
  private readonly string _connectionString;

  public RosterService(IConfiguration configuration)
  {
    var dbPath = configuration["DatabasePath"] ?? Path.Combine("data", "planner.sqlite");
    _connectionString = $"Data Source={dbPath}";
  }

  public async Task<string?> GetTeamNameAsync()
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = "SELECT name FROM team WHERE player IS NOT NULL LIMIT 1";
    var result = await command.ExecuteScalarAsync();
    return result as string;
  }

  public async Task<List<RiderAssignedRace>> GetAllAssignedRacesAsync()
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT rc.id,
                   rc.name,
                   rc.abbreviation,
                   rc.start_date,
                   rc.end_date,
                   (SELECT COUNT(*) FROM stage WHERE race_id = rc.id) AS stage_count,
                   rc.race_class_constant,
                   rc.calendar_color
            FROM race rc
            WHERE rc.id IN (
                SELECT DISTINCT race_id FROM optimise_assignment
                WHERE run_id = (SELECT MAX(id) FROM optimise_run)
            )
            ORDER BY rc.start_date
            """;

    var races = new List<RiderAssignedRace>();
    await using var reader = await command.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
      var startDate = DateOnly.Parse(reader.GetString(3));
      var endDate = DateOnly.Parse(reader.GetString(4));
      races.Add(new RiderAssignedRace(
          reader.GetInt32(0),
          reader.GetString(1),
          reader.IsDBNull(2) ? reader.GetString(1) : reader.GetString(2),
          startDate,
          endDate,
          reader.GetInt32(5),
          reader.IsDBNull(6) ? "unknown" : reader.GetString(6),
          reader.IsDBNull(7) ? "B0B0B0" : reader.GetString(7)));
    }
    return races;
  }

  public async Task<List<RiderRaceDays>> GetRosterAsync()
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT r.id, r.display_name, COUNT(s.id) AS race_days
            FROM rider r
            JOIN optimise_assignment oa ON oa.rider_id = r.id
            JOIN stage s ON s.race_id = oa.race_id
            WHERE oa.run_id = (SELECT MAX(id) FROM optimise_run)
              AND r.team_id = (SELECT id FROM team WHERE player IS NOT NULL LIMIT 1)
            GROUP BY r.id, r.display_name
            ORDER BY r.display_name
            """;

    var roster = new List<RiderRaceDays>();
    await using var reader = await command.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
      roster.Add(new RiderRaceDays(reader.GetInt32(0), reader.GetString(1), reader.GetInt32(2)));
    }
    return roster;
  }

  public async Task<RiderDetail?> GetRiderDetailAsync(int riderId)
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT r.id, r.display_name, r.age,
                   rs.flat, rs.hill, rs.medium_mountain, rs.mountain,
                   rs.time_trial, rs.prologue, rs.cobble,
                   rs.sprint, rs.acceleration,
                   rs.stamina, rs.resistance, rs.recovery, rs.baroudeur
            FROM rider r
            LEFT JOIN rider_stat rs ON rs.rider_id = r.id
            WHERE r.id = @riderId
            """;
    command.Parameters.AddWithValue("@riderId", riderId);

    await using var reader = await command.ExecuteReaderAsync();
    if (!await reader.ReadAsync()) return null;

    static int? NullableInt(SqliteDataReader r, int col) =>
        r.IsDBNull(col) ? null : r.GetInt32(col);

    return new RiderDetail(
        reader.GetInt32(0),
        reader.GetString(1),
        NullableInt(reader, 2),
        NullableInt(reader, 3), NullableInt(reader, 4), NullableInt(reader, 5), NullableInt(reader, 6),
        NullableInt(reader, 7), NullableInt(reader, 8), NullableInt(reader, 9),
        NullableInt(reader, 10), NullableInt(reader, 11),
        NullableInt(reader, 12), NullableInt(reader, 13), NullableInt(reader, 14), NullableInt(reader, 15));
  }

  public async Task<List<RiderAssignedRace>> GetRiderAssignedRacesAsync(int riderId)
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT rc.id,
                   rc.name,
                   rc.abbreviation,
                   rc.start_date,
                   rc.end_date,
                   COUNT(s.id) AS stage_count,
                   rc.race_class_constant,
                   rc.calendar_color
            FROM race rc
            JOIN optimise_assignment oa ON oa.race_id = rc.id
            JOIN stage s ON s.race_id = rc.id
            WHERE oa.rider_id = @riderId
              AND oa.run_id = (SELECT MAX(id) FROM optimise_run)
            GROUP BY rc.id, rc.name, rc.abbreviation, rc.start_date, rc.end_date, rc.level, rc.calendar_color
            ORDER BY rc.start_date
            """;
    command.Parameters.AddWithValue("@riderId", riderId);

    var races = new List<RiderAssignedRace>();
    await using var reader = await command.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
      var startDate = DateOnly.Parse(reader.GetString(3));
      var endDate = DateOnly.Parse(reader.GetString(4));
      races.Add(new RiderAssignedRace(
          reader.GetInt32(0),
          reader.GetString(1),
          reader.IsDBNull(2) ? reader.GetString(1) : reader.GetString(2),
          startDate,
          endDate,
          reader.GetInt32(5),
          reader.IsDBNull(6) ? "unknown" : reader.GetString(6),
          reader.IsDBNull(7) ? "B0B0B0" : reader.GetString(7)));
    }
    return races;
  }

  public async Task<RaceDetail?> GetRaceDetailAsync(int raceId)
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    // Race header
    await using var raceCmd = connection.CreateCommand();
    raceCmd.CommandText = """
            SELECT id, name, start_date, end_date
            FROM race
            WHERE id = @raceId
            """;
    raceCmd.Parameters.AddWithValue("@raceId", raceId);

    await using var raceReader = await raceCmd.ExecuteReaderAsync();
    if (!await raceReader.ReadAsync()) return null;

    var name = raceReader.GetString(1);
    var startDate = DateOnly.Parse(raceReader.GetString(2));
    var endDate = DateOnly.Parse(raceReader.GetString(3));
    await raceReader.CloseAsync();

    // Stages ordered by stage_number
    await using var stageCmd = connection.CreateCommand();
    stageCmd.CommandText = """
            SELECT stage_number, relief, stage_type
            FROM stage
            WHERE race_id = @raceId
            ORDER BY stage_number
            """;
    stageCmd.Parameters.AddWithValue("@raceId", raceId);

    var stages = new List<RaceStage>();
    await using var stageReader = await stageCmd.ExecuteReaderAsync();
    while (await stageReader.ReadAsync())
    {
      stages.Add(new RaceStage(
          stageReader.GetInt32(0),
          stageReader.IsDBNull(1) ? null : stageReader.GetString(1),
          stageReader.IsDBNull(2) ? null : stageReader.GetString(2)));
    }
    await stageReader.CloseAsync();

    // Riders assigned from latest optimise run
    await using var ridersCmd = connection.CreateCommand();
    ridersCmd.CommandText = """
            SELECT r.id, r.display_name
            FROM rider r
            JOIN optimise_assignment oa ON oa.rider_id = r.id
            WHERE oa.race_id = @raceId
              AND oa.run_id = (SELECT MAX(id) FROM optimise_run)
            ORDER BY r.display_name
            """;
    ridersCmd.Parameters.AddWithValue("@raceId", raceId);

    var riders = new List<RaceRider>();
    await using var ridersReader = await ridersCmd.ExecuteReaderAsync();
    while (await ridersReader.ReadAsync())
    {
      riders.Add(new RaceRider(ridersReader.GetInt32(0), ridersReader.GetString(1)));
    }

    // Optimiser values from latest run
    await using var optimiseCmd = connection.CreateCommand();
    optimiseCmd.CommandText = """
            SELECT stage_value, squad_profile
            FROM optimise_race
            WHERE race_id = @raceId
              AND run_id = (SELECT MAX(id) FROM optimise_run)
            """;
    optimiseCmd.Parameters.AddWithValue("@raceId", raceId);

    int? stageValue = null;
    string? squadProfile = null;
    await using var optimiseReader = await optimiseCmd.ExecuteReaderAsync();
    if (await optimiseReader.ReadAsync())
    {
      stageValue = optimiseReader.IsDBNull(0) ? null : optimiseReader.GetInt32(0);
      squadProfile = optimiseReader.IsDBNull(1) ? null : optimiseReader.GetString(1);
    }

    return new RaceDetail(raceId, name, startDate, endDate, stages, riders, stageValue, squadProfile);
  }

  public async Task<List<RiderCalendarEntry>> GetAllRiderCalendarEntriesAsync()
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT r.id,
                   r.display_name,
                   rc.id,
                   rc.name,
                   rc.abbreviation,
                   rc.start_date,
                   rc.end_date,
                   COUNT(s.id) AS stage_count,
                   rc.race_class_constant,
                   rc.calendar_color
            FROM rider r
            JOIN optimise_assignment oa ON oa.rider_id = r.id
            JOIN race rc ON rc.id = oa.race_id
            JOIN stage s ON s.race_id = rc.id
            WHERE oa.run_id = (SELECT MAX(id) FROM optimise_run)
              AND r.team_id = (SELECT id FROM team WHERE player IS NOT NULL LIMIT 1)
            GROUP BY r.id, r.display_name, rc.id, rc.name, rc.abbreviation,
                     rc.start_date, rc.end_date, rc.race_class_constant, rc.calendar_color
            ORDER BY r.display_name, rc.start_date
            """;

    var riderMap = new Dictionary<int, (string Name, List<RiderAssignedRace> Races)>();
    var riderOrder = new List<int>();

    await using var reader = await command.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
      var riderId = reader.GetInt32(0);
      var riderName = reader.GetString(1);
      var startDate = DateOnly.Parse(reader.GetString(5));
      var endDate = DateOnly.Parse(reader.GetString(6));
      var race = new RiderAssignedRace(
          reader.GetInt32(2),
          reader.GetString(3),
          reader.IsDBNull(4) ? reader.GetString(3) : reader.GetString(4),
          startDate,
          endDate,
          reader.GetInt32(7),
          reader.IsDBNull(8) ? "unknown" : reader.GetString(8),
          reader.IsDBNull(9) ? "B0B0B0" : reader.GetString(9));

      if (!riderMap.ContainsKey(riderId))
      {
        riderMap[riderId] = (riderName, []);
        riderOrder.Add(riderId);
      }
      riderMap[riderId].Races.Add(race);
    }

    return riderOrder
        .Select(id => new RiderCalendarEntry(id, riderMap[id].Name, riderMap[id].Races))
        .ToList();
  }

  public async Task<SeasonSummary?> GetSeasonSummaryAsync()
  {
    await using var connection = new SqliteConnection(_connectionString);
    await connection.OpenAsync();

    await using var command = connection.CreateCommand();
    command.CommandText = """
            SELECT
                CAST(strftime('%Y', MIN(rc.start_date)) AS INTEGER) AS season,
                COUNT(DISTINCT oa.race_id)                          AS race_count,
                (SELECT COUNT(*) FROM rider
                 WHERE team_id = (SELECT id FROM team WHERE player IS NOT NULL LIMIT 1)) AS rider_count,
                CAST(COUNT(s.id) AS REAL) / COUNT(DISTINCT oa.rider_id) AS avg_race_days
            FROM optimise_assignment oa
            JOIN race rc ON rc.id = oa.race_id
            JOIN stage s  ON s.race_id  = oa.race_id
            WHERE oa.run_id = (SELECT MAX(id) FROM optimise_run)
            """;

    await using var reader = await command.ExecuteReaderAsync();
    if (!await reader.ReadAsync() || reader.IsDBNull(0)) return null;

    return new SeasonSummary(
        reader.GetInt32(0),
        reader.GetInt32(1),
        reader.GetInt32(2),
        reader.GetDouble(3));
  }
}
