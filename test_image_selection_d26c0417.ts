
import { chooseClusterImage } from './web/src/utils/imageSelection';

const cluster = {
    cluster_id: "d26c0417",
    representative_image: "https://makfax.com.mk/wp-content/uploads/2026/04/depositphotos_655659780_s.webp",
    articles: [
        { source: "4News", image_url: "https://4news.mk/wp-content/uploads/2026/04/screenshot_4-7-1024x635.avif" },
        { source: "Makfax", image_url: "https://makfax.com.mk/wp-content/uploads/2026/04/depositphotos_655659780_s.webp" },
        { source: "Nezavisen", image_url: "https://nezavisen.mk/wp-content/uploads/2026/04/kral-carls-tramp.jpg" },
        { source: "Tocka", image_url: "https://tocka.com.mk/images/content/golemi/2026-04/fXFhB-.png" },
        { source: "Kanal77", image_url: "https://kanal77.mk/wp-content/uploads/2026/04/tramp-i-kral-charls-1024x683.jpg" }
    ]
};

console.log(JSON.stringify(chooseClusterImage(cluster, 'hero'), null, 2));
