import React, { useState, useEffect, useRef } from 'react';
import { 
  User, 
  Mail, 
  Link2, 
  Calendar, 
  Image as ImageIcon, 
  Calculator, 
  Sparkles, 
  AlertCircle,
  FileImage,
  ArrowRight,
  TrendingUp
} from 'lucide-react';
import { localePathForLang } from '../../lib/localePaths';
import { buildCsrfHeadersAsync } from '../../lib/personalization';
import { CPM_RATES_EUR, CPM_BASE_EUR, PROMO_PERCENT, localCpm } from '../../lib/adPricing';

interface AdBookingFormProps {
  lang: 'sr' | 'mk';
}

const CPM_RATES = CPM_RATES_EUR;
const CPM_BASE = CPM_BASE_EUR;
// Keep in sync with MIN_CHARGE_CENTS in routes/marketing.py.
const MIN_CHECKOUT_EUR = 30;

const translations = {
  mk: {
    title: 'Резервирајте реклама',
    subtitle: 'Целосно автоматизиран систем за самостојно објавување рекламни банери',
    name: 'Име и презиме',
    email: 'Е-пошта',
    slot: 'Изберете тип на банер',
    url: 'Линк за насочување (Target URL)',
    startDate: 'Датум на почеток',
    endDate: 'Датум на крај',
    impressions: 'Вкупен број на импресии',
    file: 'Прикачете банер (Макс. 150KB)',
    cpm: 'CPM цена',
    dailyAverage: 'Просечно импресии дневно',
    totalDays: 'Вкупно денови',
    totalPrice: 'Вкупна цена за плаќање',
    minCheckoutError: `Минималниот износ за плаќање е €${MIN_CHECKOUT_EUR}.`,
    minDailyError: 'Минималниот просечен број на импресии дневно е 2,000.',
    dateError: 'Крајниот датум мора да биде почетниот датум или подоцна.',
    futureDateError: 'Почетниот датум не може да биде во минатото.',
    fileSizeError: 'Големината на фајлот ја надминува границата од 150KB.',
    fileTypeError: 'Невалиден тип на фајл. Дозволени се само слики (png, jpg, jpeg, gif, webp).',
    submit: 'Продолжи кон плаќање (Stripe)',
    submitting: 'Се процесира...',
    success: 'Успешна резервација!',
    error: 'Настана грешка. Обидете се повторно.',
    top_banner_desc: 'Голем банер на врвот на страницата (990x80 или 990x150). Одличен за максимална видливост.',
    sidebar_desc: 'Страничен банер (300x250 или 300x600). Се прикажува во десната колона на десктоп.',
    mobile_content_desc: 'Банер во содржината на мобилен уред (300x250). Идеален за мобилен сообраќај.',
  },
  sr: {
    title: 'Rezervišite oglas',
    subtitle: 'Potpuno automatizovan sistem za samostalno objavljivanje reklamnih banera',
    name: 'Ime i prezime',
    email: 'E-mail adresa',
    slot: 'Izaberite tip banera',
    url: 'Link za usmeravanje (Target URL)',
    startDate: 'Datum početka',
    endDate: 'Datum kraja',
    impressions: 'Ukupan broj impresija',
    file: 'Priložite baner (Maks. 150KB)',
    cpm: 'CPM cena',
    dailyAverage: 'Prosečno impresija dnevno',
    totalDays: 'Ukupno dana',
    totalPrice: 'Ukupna cena za plaćanje',
    minCheckoutError: `Minimalni iznos za plaćanje je €${MIN_CHECKOUT_EUR}.`,
    minDailyError: 'Minimalni prosečni broj impresija dnevno je 2,000.',
    dateError: 'Krajnji datum mora biti isti ili nakon početnog datuma.',
    futureDateError: 'Početni datum ne može biti u prošlosti.',
    fileSizeError: 'Veličina datoteke prelazi granicu od 150KB.',
    fileTypeError: 'Nevalidan tip datoteke. Dozvoljene su samo slike (png, jpg, jpeg, gif, webp).',
    submit: 'Nastavite na plaćanje (Stripe)',
    submitting: 'Procesiranje...',
    success: 'Uspešna rezervacija!',
    error: 'Došlo je do greške. Pokušajte ponovo.',
    top_banner_desc: 'Veliki baner na vrhu stranice (990x80 ili 990x150). Odličan za maksimalnu vidljivost.',
    sidebar_desc: 'Bočni baner (300x250 ili 300x600). Prikazuje se u desnoj koloni na desktopu.',
    mobile_content_desc: 'Baner u sadržaju na mobilnom uređaju (300x250). Idealan za mobilni saobraćaj.',
  }
};

export default function AdBookingForm({ lang }: AdBookingFormProps) {
  const t = translations[lang];
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  const [activeTab, setActiveTab] = useState<'book' | 'track'>('book');

  // Form State
  const [buyerName, setBuyerName] = useState('');
  const [buyerEmail, setBuyerEmail] = useState('');
  const [slotId, setSlotId] = useState<'top_banner' | 'sidebar' | 'mobile_content'>('top_banner');
  const [targetImpressions, setTargetImpressions] = useState(50000);
  const [targetUrl, setTargetUrl] = useState('');
  const [startDate, setStartDate] = useState(todayStr);
  const [endDate, setEndDate] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);

  // Track State
  const [lookupId, setLookupId] = useState('');
  const [requestEmail, setRequestEmail] = useState('');
  const [trackStatus, setTrackStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null);
  const [isTrackSubmitting, setIsTrackSubmitting] = useState(false);

  // Validation / Calculation State
  const [numDays, setNumDays] = useState(1);
  const [dailyAvg, setDailyAvg] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Stable per-form idempotency token. Retried submissions reuse it so the
  // backend/Stripe return the original session instead of charging twice.
  const idempotencyKeyRef = useRef<string>('');
  if (!idempotencyKeyRef.current) {
    idempotencyKeyRef.current =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `ad_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  }

  const handleRequestAccess = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!requestEmail) return;
    setIsTrackSubmitting(true);
    setTrackStatus(null);
    
    try {
      const formData = new FormData();
      formData.append('email', requestEmail);
      const csrfHeaders = await buildCsrfHeadersAsync();
      
      const res = await fetch('/api/marketing/request-access', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin',
        headers: csrfHeaders,
      });
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || (lang === 'mk' ? 'Настана грешка' : 'Došlo je do greške'));
      }
      
      setTrackStatus({
        type: 'success',
        message: data.message || (lang === 'mk' ? 'Линкот е испратен!' : 'Link je poslat!')
      });
    } catch (err: any) {
      setTrackStatus({
        type: 'error',
        message: err.message
      });
    } finally {
      setIsTrackSubmitting(false);
    }
  };

  const handleLookupRedirect = (e: React.FormEvent) => {
    e.preventDefault();
    if (!lookupId.trim()) return;
    const statusUrl = localePathForLang(`/marketing/status?id=${encodeURIComponent(lookupId.trim())}`, lang);
    window.location.href = statusUrl;
  };

  // Auto-set default end date (e.g. today + 6 days for 7 days total)
  useEffect(() => {
    const start = new Date(startDate);
    if (!isNaN(start.getTime())) {
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      setEndDate(end.toISOString().split('T')[0]);
    }
  }, [startDate]);

  // Recalculate metrics on input changes
  useEffect(() => {
    if (!startDate || !endDate) return;

    const startParts = startDate.split('-');
    const endParts = endDate.split('-');
    let days = 0;

    if (startParts.length === 3 && endParts.length === 3) {
      const startYear = parseInt(startParts[0], 10);
      const startMonth = parseInt(startParts[1], 10) - 1;
      const startDay = parseInt(startParts[2], 10);
      
      const endYear = parseInt(endParts[0], 10);
      const endMonth = parseInt(endParts[1], 10) - 1;
      const endDay = parseInt(endParts[2], 10);
      
      const startUTC = Date.UTC(startYear, startMonth, startDay);
      const endUTC = Date.UTC(endYear, endMonth, endDay);
      
      const diffTime = endUTC - startUTC;
      days = diffTime >= 0 ? Math.round(diffTime / (1000 * 60 * 60 * 24)) + 1 : 0;
    }
    
    setNumDays(days);

    if (days > 0) {
      setDailyAvg(Math.round(targetImpressions / days));
      const cpm = CPM_RATES[slotId];
      setTotalCost(Math.round((targetImpressions / 1000) * cpm * 100) / 100);
    } else {
      setDailyAvg(0);
      setTotalCost(0);
    }
  }, [startDate, endDate, targetImpressions, slotId]);

  // Handle file select
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const selectedFile = files[0];
      
      // Validation size: 150KB
      if (selectedFile.size > 150 * 1024) {
        alert(t.fileSizeError);
        return;
      }

      // Validation type
      const ext = selectedFile.name.split('.').pop()?.toLowerCase();
      if (!ext || !['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
        alert(t.fileTypeError);
        return;
      }

      setFile(selectedFile);
      const reader = new FileReader();
      reader.onloadend = () => {
        setFilePreview(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  // Perform Form Submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: string[] = [];

    // Client-side validations
    if (startDate < todayStr) {
      newErrors.push(t.futureDateError);
    }
    if (endDate < startDate) {
      newErrors.push(t.dateError);
    }
    if (dailyAvg < 2000) {
      newErrors.push(t.minDailyError);
    }
    if (totalCost < MIN_CHECKOUT_EUR) {
      newErrors.push(t.minCheckoutError);
    }
    if (!file) {
      newErrors.push(lang === 'mk' ? 'Ве молиме прикачете слика за банерот.' : 'Molimo priložite sliku za baner.');
    }

    if (newErrors.length > 0) {
      setErrors(newErrors);
      // Scroll to errors
      window.scrollTo({ top: 200, behavior: 'smooth' });
      return;
    }

    setErrors([]);
    setIsSubmitting(true);

    try {
      const formData = new FormData();
      formData.append('buyer_name', buyerName);
      formData.append('buyer_email', buyerEmail);
      formData.append('slot_id', slotId);
      formData.append('target_impressions', String(targetImpressions));
      formData.append('target_url', targetUrl);
      formData.append('start_date', startDate);
      formData.append('end_date', endDate);
      formData.append('idempotency_key', idempotencyKeyRef.current);
      if (file) {
        formData.append('file', file);
      }

      const csrfHeaders = await buildCsrfHeadersAsync();

      const res = await fetch('/api/marketing/checkout', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin',
        headers: csrfHeaders,
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || t.error);
      }

      const data = await res.json();
      if (data.checkout_url) {
        // Redirect to Stripe Checkout or local developer mock success page
        window.location.href = data.checkout_url;
      } else {
        throw new Error('No checkout URL received');
      }
    } catch (err: any) {
      console.error(err);
      setErrors([err.message || t.error]);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-8">
      {/* Header section */}
      <div className="text-center mb-12">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-none text-xs font-semibold bg-[var(--presek-mark-soft)] text-[var(--presek-mark)] border border-[var(--presek-mark-line)] mb-4 uppercase tracking-wider">
          <Sparkles className="w-3.5 h-3.5" />
          {lang === 'mk' ? 'Самопослужен Маркетинг' : 'Samouslužni Marketing'}
        </span>
        <h1 className="text-4xl md:text-5xl font-black tracking-tight text-foreground mb-4 font-serif">
          {t.title}
        </h1>
        <p className="text-muted-foreground max-w-2xl mx-auto text-base md:text-lg font-sans">
          {t.subtitle}
        </p>
      </div>

      {/* Tab Switcher */}
      <div className="flex justify-center mb-8 border-b border-border">
        <button
          type="button"
          onClick={() => { setActiveTab('book'); setTrackStatus(null); }}
          className={`px-6 py-3 font-serif font-bold text-base border-b-2 transition-all cursor-pointer ${
            activeTab === 'book'
              ? 'border-[var(--presek-mark)] text-[var(--presek-mark)]'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          {lang === 'mk' ? 'Резервација на реклама' : 'Rezervacija oglasa'}
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('track'); setTrackStatus(null); }}
          className={`px-6 py-3 font-serif font-bold text-base border-b-2 transition-all cursor-pointer ${
            activeTab === 'track'
              ? 'border-[var(--presek-mark)] text-[var(--presek-mark)]'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          {lang === 'mk' ? 'Следи кампања' : 'Prati kampanju'}
        </button>
      </div>

      {activeTab === 'book' ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Form panel */}
          <form onSubmit={handleSubmit} className="lg:col-span-8 bg-card border border-border rounded-none p-6 md:p-8 space-y-6">
            {errors.length > 0 && (
              <div className="bg-destructive/10 border border-destructive/20 rounded-none p-4 text-destructive flex gap-3 font-sans">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <div>
                  <h5 className="font-bold text-sm mb-1">{lang === 'mk' ? 'Внимание' : 'Pažnja'}</h5>
                  <ul className="list-disc pl-4 text-xs space-y-1">
                    {errors.map((err, idx) => <li key={idx}>{err}</li>)}
                  </ul>
                </div>
              </div>
            )}

            {/* Step 1: Customer details */}
            <div className="space-y-4 font-sans">
              <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
                <User className="w-5 h-5 text-[var(--presek-mark)]" />
                {lang === 'mk' ? '1. Контакт информации' : '1. Kontakt informacije'}
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.name}</label>
                  <div className="relative">
                    <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="text" 
                      required
                      value={buyerName}
                      onChange={(e) => setBuyerName(e.target.value)}
                      placeholder="e.g. Petar Petrovski" 
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.email}</label>
                  <div className="relative">
                    <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="email" 
                      required
                      value={buyerEmail}
                      onChange={(e) => setBuyerEmail(e.target.value)}
                      placeholder="e.g. petar@example.com" 
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Step 2: Slot Selection */}
            <div className="space-y-4 font-sans">
              <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
                <ImageIcon className="w-5 h-5 text-[var(--presek-mark)]" />
                {lang === 'mk' ? '2. Избор на позиција' : '2. Izbor pozicije'}
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {(['top_banner', 'sidebar', 'mobile_content'] as const).map((type) => {
                  const active = slotId === type;
                  const price = CPM_RATES[type];
                  const sizeStr = type === 'top_banner' ? '990x80 / 990x150' : type === 'sidebar' ? '300x250 / 300x600' : '300x250';
                  
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setSlotId(type)}
                      className={`flex flex-col text-left p-4 rounded-none border transition-all relative overflow-hidden group cursor-pointer ${
                        active 
                          ? 'bg-[var(--presek-mark-soft)] border-[var(--presek-mark)]' 
                          : 'bg-card border-border hover:border-[var(--presek-mark-line)] hover:bg-[var(--presek-mark-soft)]/20'
                      }`}
                    >
                      <div className="flex justify-between items-start w-full mb-1">
                        <span className={`font-bold text-sm ${active ? 'text-[var(--presek-mark)]' : 'text-foreground'}`}>
                          {type.replace('_', ' ').toUpperCase()}
                        </span>
                        <span className="text-xs font-extrabold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-none">
                          €{price.toFixed(2)} CPM
                        </span>
                      </div>
                      <span className="text-muted-foreground/60 text-xxs font-mono mb-2">{sizeStr}</span>
                      <span className="text-muted-foreground text-xs leading-relaxed shrink-0">
                        {t[`${type}_desc` as keyof typeof t]}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 3: Target Details */}
            <div className="space-y-4 font-sans">
              <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
                <Link2 className="w-5 h-5 text-[var(--presek-mark)]" />
                {lang === 'mk' ? '3. Детали за кампањата' : '3. Detalji kampanje'}
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.url}</label>
                  <div className="relative">
                    <Link2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="url" 
                      required
                      value={targetUrl}
                      onChange={(e) => setTargetUrl(e.target.value)}
                      placeholder="https://yourwebsite.com/landing" 
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.startDate}</label>
                  <div className="relative">
                    <Calendar className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="date" 
                      required
                      min={todayStr}
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors text-foreground"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.endDate}</label>
                  <div className="relative">
                    <Calendar className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="date" 
                      required
                      min={startDate}
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors text-foreground"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.impressions}</label>
                  <div className="relative">
                    <TrendingUp className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
                    <input 
                      type="number" 
                      required
                      step={1000}
                      min={1000}
                      value={targetImpressions || ''}
                      onChange={(e) => setTargetImpressions(e.target.value === '' ? 0 : Math.max(0, Number(e.target.value)))}
                      className="w-full bg-card border border-border rounded-none py-2.5 pl-10 pr-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40"
                    />
                  </div>
                </div>

                {/* Upload field */}
                <div>
                  <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{t.file}</label>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full bg-card border border-border border-dashed hover:border-[var(--presek-mark-line)] hover:bg-[var(--presek-mark-soft)]/10 rounded-none py-2.5 px-4 text-muted-foreground text-sm focus:outline-none transition-colors flex items-center justify-between text-left cursor-pointer"
                  >
                    <span className="truncate max-w-[80%]">
                      {file ? file.name : (lang === 'mk' ? 'Изберете слика...' : 'Izaberite sliku...')}
                    </span>
                    <FileImage className="w-4 h-4 text-[var(--presek-mark)] shrink-0" />
                  </button>
                  <input 
                    type="file" 
                    ref={fileInputRef}
                    accept="image/*"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </div>
              </div>
            </div>
          </form>

          {/* Calculation Details and Checkout Panel */}
          <div className="lg:col-span-4 bg-card border border-border rounded-none p-6 md:p-8 space-y-6 sticky top-8 font-sans">
            <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
              <Calculator className="w-5 h-5 text-[var(--presek-mark)]" />
              {lang === 'mk' ? 'Калкулатор и Преглед' : 'Kalkulator i Pregled'}
            </h3>

            {filePreview && (
              <div className="space-y-2">
                <span className="block text-xxs font-bold text-muted-foreground uppercase tracking-wider">
                  {lang === 'mk' ? 'Преглед на Банер' : 'Pregled Banera'}
                </span>
                <div className="border border-border rounded-none bg-muted/30 p-2 flex items-center justify-center min-h-[100px]">
                  <img src={filePreview} alt="Preview" className="max-h-[150px] object-contain rounded-none" />
                </div>
              </div>
            )}

            <div className="space-y-3 font-mono text-sm">
              <div className="flex justify-between text-muted-foreground">
                <span>{t.cpm}:</span>
                <span className="text-foreground font-bold">€{CPM_RATES[slotId].toFixed(2)} <span className="text-muted-foreground/50 text-xxs font-normal line-through">€{CPM_BASE[slotId].toFixed(2)}</span> <span className="text-emerald-600 dark:text-emerald-400 text-xxs font-bold">−{PROMO_PERCENT}%</span> <span className="text-muted-foreground/60 text-xxs font-normal">(~{localCpm(CPM_RATES[slotId], lang).amount} {localCpm(CPM_RATES[slotId], lang).currency})</span></span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>{t.totalDays}:</span>
                <span className="text-foreground font-bold">{numDays}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>{t.dailyAverage}:</span>
                <span className={`font-bold ${dailyAvg < 2000 ? 'text-amber-600 dark:text-amber-400' : 'text-foreground'}`}>
                  {dailyAvg.toLocaleString()}
                </span>
              </div>
              <div className="border-t border-border pt-3 flex justify-between text-base font-sans">
                <span className="text-foreground font-semibold">{t.totalPrice}:</span>
                <span className={`font-bold text-lg ${totalCost < MIN_CHECKOUT_EUR ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                  €{totalCost.toFixed(2)} <span className="text-sm font-normal text-muted-foreground/60">(~{Math.round((targetImpressions / 1000) * localCpm(CPM_RATES[slotId], lang).amount).toLocaleString()} {localCpm(CPM_RATES[slotId], lang).currency})</span>
                </span>
              </div>
            </div>

            {/* Validation Warnings */}
            <div className="space-y-2 text-xxs leading-relaxed">
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-none bg-muted/40 border border-border text-muted-foreground">
                <div className={`w-1.5 h-1.5 shrink-0 ${dailyAvg >= 2000 ? 'bg-emerald-600 dark:bg-emerald-400' : 'bg-amber-600 dark:bg-amber-400'}`} />
                <span>{lang === 'mk' ? 'Минимум 2,000 импресии/ден' : 'Minimum 2,000 impresija/dan'}</span>
              </div>
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-none bg-muted/40 border border-border text-muted-foreground">
                <div className={`w-1.5 h-1.5 shrink-0 ${totalCost >= MIN_CHECKOUT_EUR ? 'bg-emerald-600 dark:bg-emerald-400' : 'bg-amber-600 dark:bg-amber-400'}`} />
                <span>{lang === 'mk' ? `Минимум €${MIN_CHECKOUT_EUR} плаќање` : `Minimum €${MIN_CHECKOUT_EUR} plaćanje`}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="w-full bg-[var(--presek-mark)] hover:bg-[var(--presek-mark)]/90 text-white font-bold py-3 px-4 rounded-none active:scale-[0.99] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2 cursor-pointer"
            >
              {isSubmitting ? t.submitting : (
                <>
                  {t.submit}
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        <div className="max-w-xl mx-auto w-full bg-card border border-border p-6 md:p-8 space-y-8 font-sans">
          {/* Section 1: Direct ID Lookup */}
          <form onSubmit={handleLookupRedirect} className="space-y-4">
            <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
              <Calculator className="w-5 h-5 text-[var(--presek-mark)]" />
              {lang === 'mk' ? 'Прегледај со Идентификатор' : 'Pregledaj sa ID-jem'}
            </h3>
            <div>
              <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">
                {lang === 'mk' ? 'Идентификатор на Кампања (Campaign ID)' : 'Identifikator Kampanje (Campaign ID)'}
              </label>
              <input
                type="text"
                required
                value={lookupId}
                onChange={(e) => setLookupId(e.target.value)}
                placeholder="e.g. c39c948e-28af-45e3-82a1-..."
                className="w-full bg-card border border-border rounded-none py-2.5 px-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40 font-mono"
              />
            </div>
            <button
              type="submit"
              className="w-full bg-[var(--presek-mark)] hover:bg-[var(--presek-mark)]/90 text-white font-bold py-2.5 px-4 rounded-none transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              {lang === 'mk' ? 'Пребарај' : 'Pretraži'}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <div className="relative flex py-2 items-center">
            <div className="flex-grow border-t border-border"></div>
            <span className="flex-shrink mx-4 text-xs text-muted-foreground font-semibold uppercase tracking-wider">{lang === 'mk' ? 'ИЛИ' : 'ILI'}</span>
            <div className="flex-grow border-t border-border"></div>
          </div>

          {/* Section 2: Request Access links to email */}
          <form onSubmit={handleRequestAccess} className="space-y-4">
            <h3 className="text-lg font-bold text-foreground border-b border-border pb-2 flex items-center gap-2 font-serif">
              <Mail className="w-5 h-5 text-[var(--presek-mark)]" />
              {lang === 'mk' ? 'Испрати линкови на е-пошта' : 'Pošalji linkove na e-mail'}
            </h3>
            <p className="text-muted-foreground text-xs leading-relaxed">
              {lang === 'mk' 
                ? 'Внесете ја е-поштата со која ги резервиравте кампањите. Ќе ви испратиме е-порака со сите ваши активни линкови за статистика.'
                : 'Unesite e-mail sa kojim ste rezervisali kampanje. Poslaćemo vam e-poruku sa svim vašim aktivnim linkovima za statistiku.'}
            </p>
            
            {trackStatus && (
              <div className={`p-4 rounded-none text-sm font-sans ${
                trackStatus.type === 'success' 
                  ? 'bg-emerald-50 border border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800/30 text-emerald-800 dark:text-emerald-400'
                  : 'bg-destructive/10 border border-destructive/20 text-destructive'
              }`}>
                {trackStatus.message}
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">
                {lang === 'mk' ? 'Вашата е-пошта' : 'Vaša e-mail adresa'}
              </label>
              <input
                type="email"
                required
                value={requestEmail}
                onChange={(e) => setRequestEmail(e.target.value)}
                placeholder="e.g. petar@example.com"
                className="w-full bg-card border border-border rounded-none py-2.5 px-4 text-foreground text-sm focus:outline-none focus:border-[var(--presek-mark)] focus:ring-1 focus:ring-[var(--presek-mark)] transition-colors placeholder:text-muted-foreground/40"
              />
            </div>
            <button
              type="submit"
              disabled={isTrackSubmitting}
              className="w-full bg-[var(--presek-mark)] hover:bg-[var(--presek-mark)]/90 text-white font-bold py-2.5 px-4 rounded-none transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2 cursor-pointer"
            >
              {isTrackSubmitting ? (lang === 'mk' ? 'Се испраќа...' : 'Slanje...') : (
                <>
                  {lang === 'mk' ? 'Испрати пристапни линкови' : 'Pošalji pristupne linkove'}
                  <Mail className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
