export const AdsKeeperWidget = () => {
    return (
        <div className="adskeeper-container my-8">
            {/* Desktop Widget */}
            <div className="adskeeper-desktop hidden md:block">
                <div data-type="_mgwidget" data-widget-id="2006214"></div>
                <script dangerouslySetInnerHTML={{ __html: `(function(w,q){w[q]=w[q]||[];w[q].push(["_mgc.load"])})(window,"_mgq");` }}></script>
            </div>
            
            {/* Mobile Widget */}
            <div className="adskeeper-mobile block md:hidden">
                <div data-type="_mgwidget" data-widget-id="2006241"></div>
                <script dangerouslySetInnerHTML={{ __html: `(function(w,q){w[q]=w[q]||[];w[q].push(["_mgc.load"])})(window,"_mgq");` }}></script>
            </div>
        </div>
    );
};
