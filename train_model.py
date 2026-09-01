import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
import xgboost as xgb
import joblib

# تولید داده مصنوعی (۱۰۰۰۰ رکورد)
np.random.seed(42)
n = 10000

data = {
    'temperature': np.random.normal(170, 25, n),
    'pressure': np.random.normal(5.5, 1.5, n),
    'flow_rate': np.random.normal(200, 50, n),
    'level': np.random.uniform(20, 80, n)
}
df = pd.DataFrame(data)

# برچسب‌زنی بر اساس قوانین HAZOP
def assign_risk(row):
    if row['temperature'] > 190 or row['pressure'] > 7.5:
        return 2  # High
    elif row['temperature'] > 170 or row['pressure'] > 6.0 or row['flow_rate'] > 250:
        return 1  # Medium
    else:
        return 0  # Low

df['risk'] = df.apply(assign_risk, axis=1)

X = df[['temperature', 'pressure', 'flow_rate', 'level']]
y = df['risk']

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

model = xgb.XGBClassifier(objective='multi:softmax', num_class=3, n_estimators=100)
model.fit(X_train, y_train)

accuracy = model.score(X_test, y_test)
print(f"مدل XGBoost با دقت {accuracy:.2%} آموزش دید")

joblib.dump(model, 'risk_model_xgb.pkl')
joblib.dump(scaler, 'scaler.pkl')

print("مدل ذخیره شد: risk_model_xgb.pkl")