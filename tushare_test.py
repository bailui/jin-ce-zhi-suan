# ======================
# Tushare Token: 复制下面第4到7行代码，导入到项目代码中
# ======================
import tushare as ts
import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://tushare.xyz" # 一定要加上这行代码，否则会报错
pro = ts.pro_api('4ba065ecb8eebdebc93dffaef6bc051eeb3a98b46eb7d94fd697282f') # 你的独立Token请勿泄露

# ======================
# 5000积分测试 - 日线行情
df = pro.daily(limit=20)
print(df)