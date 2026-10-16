Set-Location "D:\procon\pro26\promax26-duc"
>> 
>> python solvers\promax26_3_adapter\run_snapshot.py `
>>     --snapshot cases\master\32japan.snapshot.json `
>>     --exe solver_versions\stock_fuel_1a48c56319eb\udon_stock_fuel_runner.exe `
>>     --budget 55000 `
>>     --seed 1 `
>>     --threads 8 `
>>     --roles 0,0,0,0,1,0,0 `
>>     --cross-moves 7 `
>>     --end-spot-weight 0 `
>>     --loop-repair `
>>     --objective OFFICIAL_LEXICOGRAPHIC `
>>     --output reports\stock-fuel\hehe.json