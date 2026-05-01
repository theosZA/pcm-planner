.venv\Scripts\python.exe -m migrate ^
  --target data\planner.sqlite ^
  --lachis-export C:\Utilities\LachisEditor\Data\Career_1 ^
  --reset ^
  --import-races-and-stages ^
  --mod-stages "F:\SteamLibrary\steamapps\workshop\content\2494350\3262564567\Stages" ^
  --base-stages "F:\SteamLibrary\steamapps\common\Pro Cycling Manager 2024\CM_Stages" ^
  --stage-editor-exe "F:\SteamLibrary\steamapps\common\Pro Cycling Manager 2024 Tool\CTStageEditor.exe"
REM   Add --force-stage-export above to delete cached Stage Editor XMLs and re-export all stages.