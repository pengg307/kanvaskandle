# kanvaskandle
kanvas of kandle
使用方法

    将所有代码文件保存到同一目录下。

    将历史K线CSV文件放入 data/ 文件夹（如 AG20606_15min.csv）。

    根据实际情况调整 config.yaml 中的品种每点价值和初始资金。

    运行 python main.py 即可开始回测（目前无融合JSON输入，交易次数为0，但架构验证通过）。

    待融合JSON接入后，信号自动产生。