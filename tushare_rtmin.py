# ======================
# Tushare Token: 复制下面第4到7行代码，导入到项目代码中
# ======================
import tushare as ts
import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://tushare.xyz" # 一定要加上这行代码，否则会报错
pro = ts.pro_api('4ba065ecb8eebdebc93dffaef6bc051eeb3a98b46eb7d94fd697282f') # 你的独立Token请勿泄露

# 获取多个股票的的实时分钟数据
df = pro.rt_min(ts_code='600000.SH,600519.SH,600031.SH,000001.SZ,002594.SZ,300308.SZ')
print(df)