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

interface AdBookingFormProps {
  lang: 'sr' | 'mk';
}

const CPM_RATES: Record<string, number> = {
  top_banner: 1.00,       // ~60 MKD — 990x80 / 990x150
  sidebar: 1.25,          // ~75 MKD — 300x250 / 300x600
  mobile_content: 2.00,   // ~125 MKD — 300x250
};

const MKD_PER_EUR = 61.5;
const RSD_PER_EUR = 117.0;
const MIN_CHECKOUT_EUR = 10;

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
  const todayStr = new Date().toISOString().split('T')[0];

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

  // Validation / Calculation State
  const [numDays, setNumDays] = useState(1);
  const [dailyAvg, setDailyAvg] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [errors, setErrors] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

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

    const start = new Date(startDate);
    const end = new Date(endDate);
    
    // Clear hours for comparison
    start.setHours(0,0,0,0);
    end.setHours(0,0,0,0);

    const diffTime = end.getTime() - start.getTime();
    const days = diffTime >= 0 ? Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1 : 0;
    setNumDays(days);

    if (days > 0) {
      setDailyAvg(Math.round(targetImpressions / days));
    } else {
      setDailyAvg(0);
    }

    const cpm = CPM_RATES[slotId];
    setTotalCost(Math.round((targetImpressions / 1000) * cpm * 100) / 100);
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
    if (new Date(startDate) < new Date(todayStr)) {
      newErrors.push(t.futureDateError);
    }
    if (new Date(endDate) < new Date(startDate)) {
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
      if (file) {
        formData.append('file', file);
      }

      const res = await fetch('/api/marketing/checkout', {
        method: 'POST',
        body: formData,
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
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-4 uppercase tracking-wider">
          <Sparkles className="w-3.5 h-3.5" />
          {lang === 'mk' ? 'Самопослужен Маркетинг' : 'Samouslužni Marketing'}
        </span>
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 via-indigo-200 to-indigo-100 bg-clip-text text-transparent mb-4 font-serif">
          {t.title}
        </h1>
        <p className="text-slate-400 max-w-2xl mx-auto text-base md:text-lg">
          {t.subtitle}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Form panel */}
        <form onSubmit={handleSubmit} className="lg:col-span-8 bg-slate-900/50 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 md:p-8 space-y-6">
          {errors.length > 0 && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 flex gap-3">
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
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2 flex items-center gap-2">
              <User className="w-5 h-5 text-indigo-400" />
              {lang === 'mk' ? '1. Контакт информации' : '1. Kontakt informacije'}
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.name}</label>
                <div className="relative">
                  <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="text" 
                    required
                    value={buyerName}
                    onChange={(e) => setBuyerName(e.target.value)}
                    placeholder="e.g. Petar Petrovski" 
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors placeholder:text-slate-600"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.email}</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="email" 
                    required
                    value={buyerEmail}
                    onChange={(e) => setBuyerEmail(e.target.value)}
                    placeholder="e.g. petar@example.com" 
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors placeholder:text-slate-600"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Step 2: Slot Selection */}
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2 flex items-center gap-2">
              <ImageIcon className="w-5 h-5 text-indigo-400" />
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
                    className={`flex flex-col text-left p-4 rounded-xl border transition-all relative overflow-hidden group ${
                      active 
                        ? 'bg-indigo-500/5 border-indigo-500 shadow-[0_0_20px_-5px_rgba(99,102,241,0.2)]' 
                        : 'bg-slate-950/30 border-slate-800 hover:border-slate-700 hover:bg-slate-950/50'
                    }`}
                  >
                    <div className="flex justify-between items-start w-full mb-1">
                      <span className={`font-bold text-sm ${active ? 'text-indigo-400' : 'text-slate-300'}`}>
                        {type.replace('_', ' ').toUpperCase()}
                      </span>
                      <span className="text-xs font-extrabold text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">
                        €{price.toFixed(2)} CPM
                      </span>
                    </div>
                    <span className="text-slate-500 text-xxs font-mono mb-2">{sizeStr}</span>
                    <span className="text-slate-400 text-xs leading-relaxed shrink-0">
                      {t[`${type}_desc` as keyof typeof t]}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Step 3: Target Details */}
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2 flex items-center gap-2">
              <Link2 className="w-5 h-5 text-indigo-400" />
              {lang === 'mk' ? '3. Детали за кампањата' : '3. Detalji kampanje'}
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.url}</label>
                <div className="relative">
                  <Link2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="url" 
                    required
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    placeholder="https://yourwebsite.com/landing" 
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors placeholder:text-slate-600"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.startDate}</label>
                <div className="relative">
                  <Calendar className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="date" 
                    required
                    min={todayStr}
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors text-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.endDate}</label>
                <div className="relative">
                  <Calendar className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="date" 
                    required
                    min={startDate}
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors text-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.impressions}</label>
                <div className="relative">
                  <TrendingUp className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input 
                    type="number" 
                    required
                    step={1000}
                    min={1000}
                    value={targetImpressions}
                    onChange={(e) => setTargetImpressions(Math.max(1000, Number(e.target.value)))}
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl py-2.5 pl-10 pr-4 text-slate-200 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors placeholder:text-slate-600"
                  />
                </div>
              </div>

              {/* Upload field */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">{t.file}</label>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full bg-slate-950/60 border border-slate-800 border-dashed hover:border-slate-700 hover:bg-slate-950/80 rounded-xl py-2.5 px-4 text-slate-400 text-sm focus:outline-none transition-colors flex items-center justify-between text-left"
                >
                  <span className="truncate max-w-[80%]">
                    {file ? file.name : (lang === 'mk' ? 'Изберете слика...' : 'Izaberite sliku...')}
                  </span>
                  <FileImage className="w-4 h-4 text-indigo-400 shrink-0" />
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
        <div className="lg:col-span-4 bg-slate-900/50 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 md:p-8 space-y-6 sticky top-8">
          <h3 className="text-lg font-bold text-slate-200 border-b border-slate-800 pb-2 flex items-center gap-2">
            <Calculator className="w-5 h-5 text-indigo-400" />
            {lang === 'mk' ? 'Калкулатор и Преглед' : 'Kalkulator i Pregled'}
          </h3>

          {filePreview && (
            <div className="space-y-2">
              <span className="block text-xxs font-semibold text-slate-500 uppercase tracking-wider">
                {lang === 'mk' ? 'Преглед на Банер' : 'Pregled Banera'}
              </span>
              <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/60 p-2 flex items-center justify-center min-h-[100px]">
                <img src={filePreview} alt="Preview" className="max-h-[150px] object-contain rounded" />
              </div>
            </div>
          )}

          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between text-slate-400">
              <span>{t.cpm}:</span>
              <span className="text-slate-200 font-bold">€{CPM_RATES[slotId].toFixed(2)} <span className="text-slate-500 text-xxs font-normal">(~{Math.round(CPM_RATES[slotId] * (lang === 'mk' ? MKD_PER_EUR : RSD_PER_EUR))} {lang === 'mk' ? 'MKD' : 'RSD'})</span></span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>{t.totalDays}:</span>
              <span className="text-slate-200 font-bold">{numDays}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>{t.dailyAverage}:</span>
              <span className={`font-bold ${dailyAvg < 2000 ? 'text-amber-500' : 'text-slate-200'}`}>
                {dailyAvg.toLocaleString()}
              </span>
            </div>
            <div className="border-t border-slate-800 pt-3 flex justify-between text-base font-sans">
              <span className="text-slate-300 font-semibold">{t.totalPrice}:</span>
              <span className={`font-bold text-lg ${totalCost < MIN_CHECKOUT_EUR ? 'text-amber-500' : 'text-emerald-400'}`}>
                €{totalCost.toFixed(2)} <span className="text-sm font-normal text-slate-500">(~{Math.round(totalCost * (lang === 'mk' ? MKD_PER_EUR : RSD_PER_EUR)).toLocaleString()} {lang === 'mk' ? 'MKD' : 'RSD'})</span>
              </span>
            </div>
          </div>

          {/* Validation Warnings */}
          <div className="space-y-2 text-xxs leading-relaxed">
            <div className="flex items-center gap-2 px-2 py-1.5 rounded bg-slate-950/60 border border-slate-800 text-slate-400">
              <div className={`w-2 h-2 rounded-full shrink-0 ${dailyAvg >= 2000 ? 'bg-emerald-500' : 'bg-amber-500'}`} />
              <span>{lang === 'mk' ? 'Минимум 2,000 импресии/ден' : 'Minimum 2,000 impresija/dan'}</span>
            </div>
            <div className="flex items-center gap-2 px-2 py-1.5 rounded bg-slate-950/60 border border-slate-800 text-slate-400">
              <div className={`w-2 h-2 rounded-full shrink-0 ${totalCost >= MIN_CHECKOUT_EUR ? 'bg-emerald-500' : 'bg-amber-500'}`} />
              <span>{lang === 'mk' ? `Минимум €${MIN_CHECKOUT_EUR} плаќање` : `Minimum €${MIN_CHECKOUT_EUR} plaćanje`}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="w-full bg-gradient-to-r from-indigo-500 via-indigo-600 to-indigo-500 hover:from-indigo-600 hover:to-indigo-600 text-white font-bold py-3 px-4 rounded-xl shadow-lg shadow-indigo-500/20 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2"
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
    </div>
  );
}
