const math = (content, gloss = [], label = "") => ({
  mathml: `<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">${content}</math>`,
  gloss,
  label
});

window.LECTUREDECK = {
  meta: { title: "{{TITLE}}", section: "COURSE TITLE", opening: "OPENING" },
  slides: [
    {
      type: "title",
      title: "{{TITLE}}",
      claim: "Replace this scaffold slide in webdeck/slides.js.",
      accent: "red"
    }
  ]
};
