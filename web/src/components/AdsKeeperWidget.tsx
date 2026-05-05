export const AdsKeeperWidget = ({ placement = 'under-article' }: { placement?: 'in-article' | 'under-article' }) => {
    // Under-Article IDs (previous)
    // Desktop: 2006214, Mobile: 2006241
    
    // In-Article IDs (new)
    // Desktop: 2006251, Mobile: 2006255
    
    const desktopId = placement === 'under-article' ? '2006214' : '2006251';
    const mobileId = placement === 'under-article' ? '2006241' : '2006255';

    return (
        <div className="adskeeper-container my-8">
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
