export default {
  plugins: {
    '@tailwindcss/postcss': {}
  }
}
import tailwindcss from "@tailwindcss/postcss";
import autoprefixer from "autoprefixer";

export default {
  plugins: [tailwindcss(), autoprefixer()],
};
