# VWP Monitoring — Streamlit saja (Sigma V tetap 20)

Rumus yang diminta: **Ru = tekanan air pori / [20 × (elevasi residu − elevasi VWP)]**. Nilai 20 konstan untuk seluruh sensor. Elevasi residu historis diambil dari database hasil impor Excel, sedangkan elevasi VWP berasal dari baris elevasi di bawah koordinat. Jika selisih elevasi <= 0 atau tidak ada data elevasi residu sebelumnya, Ru tidak dihitung. Nilai tekanan air pori mengikuti rumus workbook sebelumnya. Pastikan konsistensi satuan dan validasi teknis sebelum penggunaan resmi.

Upload `app.py`, `requirements.txt`, `monitoring.db` ke root repository GitHub melalui website. Deploy `app.py` di Streamlit Community Cloud. Tidak memerlukan Supabase. Ubah F0, T0, k, b, elevasi VWP, dan serial pada menu Parameter instrumen. Nilai Sigma V dikunci 20.

**Peringatan:** penyimpanan SQLite dan foto di Streamlit Community Cloud tidak permanen; lakukan backup ZIP rutin. Jangan menimpa database yang telah berisi pembacaan baru tanpa backup.
