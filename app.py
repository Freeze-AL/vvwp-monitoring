import io, sqlite3, zipfile
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='VWP Monitoring',page_icon='💧',layout='wide')
ROOT=Path(__file__).resolve().parent
DB=ROOT/'monitoring.db'
PHOTOS=ROOT/'photos';PHOTOS.mkdir(exist_ok=True)
conn=sqlite3.connect(DB,check_same_thread=False)
conn.row_factory=sqlite3.Row
conn.execute('''CREATE TABLE IF NOT EXISTS sensors (id TEXT PRIMARY KEY, serial TEXT,f0 REAL,t0 REAL,k REAL,b REAL,elevation REAL,sigma_v REAL,notes TEXT,coord_e REAL,coord_n REAL,gamma REAL DEFAULT 20)''')
conn.execute('''CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY AUTOINCREMENT,sensor TEXT,day TEXT,freq REAL,temp REAL,m REAL,head REAL,pressure REAL,ru REAL,photo TEXT,notes TEXT,created TEXT,residue_elev REAL,sigma_calc REAL)''')
conn.execute('UPDATE sensors SET sigma_v=20, gamma=20 WHERE sigma_v IS NULL OR sigma_v!=20 OR gamma IS NULL OR gamma!=20')
conn.commit()
def table(name):return pd.read_sql_query(f'SELECT * FROM {name}',conn)
def calculate(s,f,t,z):
    m=f*f/1000
    numerator=s['k']*(m-s['f0']**2/1000)+s['b']*(t-s['t0'])
    head=numerator/9.81
    pressure=head/9.81*101.325 # mengikuti rumus workbook asal
    depth=z-s['elevation'] if z is not None and s['elevation'] is not None else None
    sigma=20.0*depth if depth is not None and depth>0 else None
    ru=pressure/sigma if sigma is not None and sigma>0 else None
    return m,head,pressure,sigma,ru

def latest_z(sensor,day):
    r=conn.execute('SELECT residue_elev FROM readings WHERE sensor=? AND day<=? AND residue_elev IS NOT NULL ORDER BY day DESC,id DESC LIMIT 1',(sensor,str(day))).fetchone()
    return r[0] if r else None

def recalc(sensor=None):
    sensors={r['id']:dict(r) for r in conn.execute('SELECT * FROM sensors').fetchall()}
    query='SELECT * FROM readings'+(' WHERE sensor=?' if sensor else '')+' ORDER BY sensor,day,id'
    rows=conn.execute(query,(sensor,) if sensor else ()).fetchall()
    last={}
    for r in rows:
        s=sensors.get(r['sensor'])
        if not s:continue
        z=r['residue_elev']
        if z is not None:last[r['sensor']]=z
        else:z=last.get(r['sensor'])
        if z is None or r['freq'] is None or r['temp'] is None:continue
        m,h,p,sigma,ru=calculate(s,r['freq'],r['temp'],z)
        conn.execute('UPDATE readings SET m=?,head=?,pressure=?,sigma_calc=?,ru=? WHERE id=?',(m,h,p,sigma,ru,r['id']))
    conn.commit()

st.title('💧 VWP Monitoring & Ru')
# Recalculate existing history once on startup when formulas/version change.
version='sigma20_fixed_v2'
conn.execute('CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)')
old=conn.execute("SELECT value FROM app_meta WHERE key='formula_version'").fetchone()
if not old or old[0]!=version:
    recalc()
    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('formula_version',?)",(version,))
    conn.commit()
st.caption('Input frekuensi dan suhu • Elevasi residu menurut tanggal • Sigma V tetap 20 × selisih elevasi • SQLite tanpa Supabase')
st.warning('Pada Streamlit Community Cloud, database dan foto lokal tidak permanen saat restart/redeploy. Unduh backup secara rutin. Jangan gunakan untuk data sensitif tanpa pengamanan akses.')
with st.sidebar:
    page=st.radio('Menu',['Dashboard','Input pembacaan','Elevasi residu','Parameter instrumen','Riwayat & ekspor','Backup & restore'])
    st.caption('Rumus sesuai permintaan: Ru = P / [20 × (Elevasi residu − Elevasi VWP)]. Sigma V tetap 20 untuk seluruh titik.')
ss=table('sensors'); rr=table('readings')
if page=='Dashboard':
    a,b,c=st.columns(3)
    a.metric('Instrumen',len(ss));b.metric('Pembacaan',len(rr));c.metric('Ru tersedia',int(rr.ru.notna().sum()))
    if not rr.empty:
        sid=st.selectbox('Titik VWP',ss.id.tolist())
        sub=rr[rr.sensor==sid].sort_values('day')
        st.line_chart(sub.set_index('day')[['pressure','ru']].rename(columns={'pressure':'Tekanan (kPa)','ru':'Ru'}))
        st.dataframe(sub[['day','freq','temp','residue_elev','sigma_calc','pressure','ru']].tail(20),hide_index=True,use_container_width=True)
        st.info('Ru kosong jika belum ada elevasi residu pada tanggal tersebut atau tinggi residu tidak positif.')
elif_dummy=False
if page=='Parameter instrumen':
    sid=st.selectbox('Pilih instrumen',ss.id.tolist())
    s=dict(conn.execute('SELECT * FROM sensors WHERE id=?',(sid,)).fetchone())
    with st.form('parameters'):
        serial=st.text_input('Serial number',s['serial'] or '')
        a,b=st.columns(2)
        with a:
            f0=st.number_input('F0 (Hz)',value=float(s['f0'] or 0),format='%.4f')
            t0=st.number_input('T0 (°C)',value=float(s['t0'] or 0),format='%.3f')
            elev=st.number_input('Elevasi VWP (m) — baris Elevasi Excel',value=float(s['elevation'] or 0),format='%.3f')
        with b:
            k=st.number_input('Koefisien k',value=float(s['k'] or 0),format='%.8f')
            coef=st.number_input('Koefisien b',value=float(s['b'] or 0),format='%.8f')
            st.number_input('Sigma V (tetap)',value=20.0,disabled=True)
        note=st.text_area('Catatan',s['notes'] or '')
        if st.form_submit_button('Simpan & hitung ulang seluruh riwayat titik ini',type='primary'):
            conn.execute('UPDATE sensors SET serial=?,f0=?,t0=?,k=?,b=?,elevation=?,sigma_v=?,gamma=?,notes=? WHERE id=?',(serial,f0,t0,k,coef,elev,20.0,20.0,note,sid));conn.commit();recalc(sid);st.success('Parameter dan hasil historis diperbarui.');st.rerun()
    st.dataframe(ss[['id','serial','elevation','sigma_v','f0','t0','k','b']],hide_index=True,use_container_width=True)
if page=='Elevasi residu':
    st.info('Kolom G Excel berisi elevasi residu berdasarkan tanggal. Anda bisa mengubahnya untuk suatu tanggal. Tanggal sesudahnya akan memakai nilai terakhir sampai ada pengukuran elevasi baru.')
    sid=st.selectbox('Titik VWP',ss.id.tolist())
    day=st.date_input('Tanggal elevasi residu',date.today())
    current=latest_z(sid,day)
    z=st.number_input('Elevasi residu (m)',value=float(current) if current is not None else 0.0,format='%.3f')
    if st.button('Simpan elevasi dan hitung ulang',type='primary'):
        # If date has readings, set the elevation on its first reading; otherwise create an elevation-only record.
        row=conn.execute('SELECT id FROM readings WHERE sensor=? AND day=? ORDER BY id LIMIT 1',(sid,str(day))).fetchone()
        if row:conn.execute('UPDATE readings SET residue_elev=? WHERE id=?',(z,row[0]))
        else:conn.execute('INSERT INTO readings(sensor,day,residue_elev,notes,created) VALUES(?,?,?,?,?)',(sid,str(day),z,'Catatan elevasi residu',datetime.now().isoformat()))
        conn.commit();recalc(sid);st.success('Elevasi diperbarui.');st.rerun()
    sub=rr[(rr.sensor==sid)&rr.residue_elev.notna()]
    st.dataframe(sub[['day','residue_elev']].drop_duplicates().sort_values('day',ascending=False),hide_index=True)
if page=='Input pembacaan':
    with st.form('input'):
        sid=st.selectbox('Titik VWP',ss.id.tolist());day=st.date_input('Tanggal',date.today())
        c1,c2=st.columns(2)
        with c1:f=st.number_input('Frekuensi (Hz)',min_value=0.01,value=2300.0,format='%.3f')
        with c2:t=st.number_input('Suhu (°C)',value=30.0,format='%.2f')
        note=st.text_area('Keterangan');photo=st.file_uploader('Foto (opsional)',type=['jpg','jpeg','png'])
        save=st.form_submit_button('Hitung dan simpan',type='primary')
    z=latest_z(sid,day)
    st.caption(f'Elevasi residu terakhir sampai {day}: {z if z is not None else "belum tersedia"} m. Tambahkan di menu Elevasi residu bila perlu.')
    if save:
        s=dict(conn.execute('SELECT * FROM sensors WHERE id=?',(sid,)).fetchone())
        if z is None:st.error('Elevasi residu belum tersedia untuk tanggal ini. Isi menu Elevasi residu dahulu.')
        else:
            m,h,p,sigma,ru=calculate(s,f,t,z)
            path=''
            if photo:
                filename=f'{sid.replace("/","-")}_{datetime.now().strftime("%Y%m%d%H%M%S")}.{photo.name.split(".")[-1].lower()}'
                (PHOTOS/filename).write_bytes(photo.getvalue());path=filename
            conn.execute('INSERT INTO readings(sensor,day,freq,temp,m,head,pressure,ru,photo,notes,created,residue_elev,sigma_calc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(sid,str(day),f,t,m,h,p,ru,path,note,datetime.now().isoformat(),None,sigma))
            conn.commit();st.success(f'Tersimpan: P = {p:.3f} kPa, 20 × ΔElevasi = {sigma:.3f}, Ru = {ru:.4f}' if ru is not None else 'Tersimpan tanpa Ru');st.rerun()
if page=='Riwayat & ekspor':
    sid=st.selectbox('Filter instrumen',['Semua']+ss.id.tolist())
    sub=rr if sid=='Semua' else rr[rr.sensor==sid]
    st.dataframe(sub.sort_values(['day','id'],ascending=False),hide_index=True,use_container_width=True)
    st.download_button('Unduh CSV',sub.to_csv(index=False).encode('utf-8-sig'),'vwp_readings.csv','text/csv')
    try:
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        bio=io.BytesIO();doc=SimpleDocTemplate(bio,pagesize=(842,595));sty=getSampleStyleSheet()
        data=[['Tanggal','Instrumen','Hz','°C','Z residu','σv kPa','P kPa','Ru']]
        for _,r in sub.sort_values('day').iterrows():
            def fmt(v,n=2):return '' if pd.isna(v) else f'{v:.{n}f}'
            data.append([str(r.day),str(r.sensor),fmt(r.freq),fmt(r.temp),fmt(r.residue_elev,3),fmt(r.sigma_calc),fmt(r.pressure),fmt(r.ru,4)])
        elements=[Paragraph('VWP Monitoring Report',sty['Title'])]
        for start in range(1,len(data),32):
            tab=Table([data[0]]+data[start:start+32],repeatRows=1,colWidths=[90,110,70,45,85,75,75,65]);tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.3,colors.grey),('FONTSIZE',(0,0),(-1,-1),8)]));elements.append(tab)
        doc.build(elements)
        st.download_button('Unduh PDF',bio.getvalue(),'vwp_report.pdf','application/pdf')
    except Exception as ex:st.error(f'Gagal membuat PDF: {ex}')
if page=='Backup & restore':
    st.warning('Backup perlu diunduh setelah setiap sesi. Data SQLite di Streamlit Cloud tidak dijamin bertahan setelah restart.')
    def backup():
        conn.commit();out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(DB,'monitoring.db')
            for p in PHOTOS.glob('*'):
                if p.is_file():z.write(p,'photos/'+p.name)
        return out.getvalue()
    st.download_button('Unduh backup ZIP',backup(),'vwp_backup.zip','application/zip')
    upload=st.file_uploader('Pilih file backup ZIP',type='zip')
    if upload and st.button('Pulihkan backup (mengganti database saat ini)'):
        with zipfile.ZipFile(io.BytesIO(upload.getvalue())) as z:
            if 'monitoring.db' not in z.namelist():st.error('Backup tidak memuat monitoring.db')
            else:
                conn.close();DB.write_bytes(z.read('monitoring.db'))
                for name in z.namelist():
                    if name.startswith('photos/') and name.count('/')==1 and not name.endswith('/'):
                        (PHOTOS/Path(name).name).write_bytes(z.read(name))
                st.success('Backup dipulihkan. Muat ulang aplikasi.');st.stop()
