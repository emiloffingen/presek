export const AdsKeeperWidget = ({ placement = 'under-article' }: { placement?: 'in-article' | 'under-article' | 'sidebar' }) => {
    // Mapping IDs
    // Under-Article: D: 2006214, M: 2006241
    // In-Article:    D: 2006251, M: 2006255
    // Sidebar:       D: 2006255, M: 2006272
    
    let desktopId = '2006214';
    let mobileId = '2006241';

    if (placement === 'in-article') {
        desktopId = '2006251';
        mobileId = '2006255';
    } else if (placement === 'sidebar') {
        desktopId = '2006255';
        mobileId = '2006272';
    }

    return (
        <div className="adskeeper-container my-8 p-4 border border-[var(--border)] bg-[var(--secondary)] rounded-sm">
            {/* Desktop Widget */}
            <div className="adskeeper-desktop hidden md:block">
                <div data-type="_mgwidget" data-widget-id={desktopId}></div>
                <script dangerouslySetInnerHTML={{ __html: `(function(w,q){w[q]=w[q]||[];w[q].push(["_mgc.load"])})(window,"_mgq");` }}></script>
            </div>
            
            {/* Mobile Widget */}
            <div className="adskeeper-mobile block md:hidden">
                <div data-type="_mgwidget" data-widget-id={mobileId}></div>
                <script dangerouslySetInnerHTML={{ __html: `(function(w,q){w[q]=w[q]||[];w[q].push(["_mgc.load"])})(window,"_mgq");` }}></script>
            </div>
        </div>
    );
};
