@echo off
:: ========================================================================
:: Disconnect RDP and Transfer Session to Local Console
:: This prevents Windows from locking or putting EarnApp to sleep when RDP is closed
:: ========================================================================
for /f "skip=1 tokens=3" %%s in ('query user %USERNAME%') do (%windir%\System32\tscon.exe %%s /dest:console)
