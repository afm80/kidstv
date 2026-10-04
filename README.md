# إعداد النظام التلقائي للفيديوهات

## الملفات المضافة:
1. `config.json` - إعدادات Firebase و YouTube API
2. `sync.py` - سكربت المزامنة
3. `.github/workflows/auto-sync.yml` - إعدادات GitHub Actions
4. `channels.txt` - قائمة القنوات والفيديوهات

## الخطوات النهائية:

### 1. رفع المشروع على GitHub
- أنشئ مستودع جديد على GitHub
- ارفع جميع الملفات (بما في ذلك المجلد الجديد .github)

### 2. إضافة Firebase Secret (اختياري للإضافية الأمان)
اذهب إلى: https://github.com/USERNAME/REPO/settings/secrets/actions
أضف Secret اسمه: `FIREBASE_CONFIG`
القيمة: محتوى config.json

### 3. تشغيل النظام
- سيبدأ العمل تلقائياً كل ساعة
- يمكنك تشغيله يدويا من GitHub Actions

## ما يفعله النظام:
- ✅ يجلب الفيديوهات من القنوات في channels.txt
- ✅ يجلب الفيديوهات من channels.txt
- ✅ يضيف البث لقسم "قنوات البث"
- ✅ يضيف الفيديوهات لقسم "فيديوهات"
- ✅ يحذف الفيديوهات المنتهية
- ✅ يمنع التكرار
