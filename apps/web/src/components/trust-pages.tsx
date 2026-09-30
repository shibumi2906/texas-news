import { FeedView, SiteFooter, SiteHeader } from "@/components/public-site";
import type { TrustPath } from "@/lib/discovery";
import type { AuthorPageData, Homepage } from "@/lib/public-api";

const copy = {
  en: {
    about: {
      title: "About us",
      lead: "Independent local reporting on entertainment and culture across Texas.",
      sections: [
        [
          "Our coverage",
          "We report on music, film, food, sports, events and the people shaping local culture. Every published story is assigned to the Texas portal and its relevant local geography.",
        ],
        [
          "Our languages",
          "English is the primary edition. Spanish stories are published only when a reviewed Spanish representation is available; missing translations are not silently substituted.",
        ],
      ],
    },
    contact: {
      title: "Contact",
      lead: "Send news tips, corrections and partnership enquiries to the newsroom.",
      sections: [
        [
          "Newsroom",
          "Use the verified contact address shown below. Do not send passwords, payment details or other sensitive personal information.",
        ],
      ],
    },
    "editorial-policy": {
      title: "Editorial policy",
      lead: "Accuracy, transparent sourcing and a clear separation between reporting and advertising guide our work.",
      sections: [
        [
          "Verification and attribution",
          "Reporters verify material facts, identify sources whenever safety permits and link to primary records where available. Headlines and summaries must accurately reflect the published story.",
        ],
        [
          "AI-assisted work",
          "AI tools may assist search, summarization and newsroom workflows. Provider output does not bypass editorial publication rules, and the canonical published article remains the source of record.",
        ],
        [
          "Advertising",
          "Sponsored material and advertising are labeled and kept separate from editorial ranking and publication decisions.",
        ],
      ],
    },
    corrections: {
      title: "Corrections policy",
      lead: "We correct material errors promptly and preserve an accountable publication record.",
      sections: [
        [
          "How corrections work",
          "Verified corrections are applied to the canonical story. Material changes update the modification date and should include an explanatory editor’s note. Retractions are removed from public eligibility rather than left discoverable as current reporting.",
        ],
        [
          "Request a correction",
          "Include the story URL, the disputed statement and supporting evidence when contacting the newsroom.",
        ],
      ],
    },
    ownership: {
      title: "Ownership and funding",
      lead: "Readers should be able to understand who publishes the site and how commercial relationships are handled.",
      sections: [
        [
          "Publisher",
          "The publication is operated under the publisher identity displayed on this site. Production deployments must publish the legal owner and funding details in the newsroom contact configuration.",
        ],
        [
          "Commercial independence",
          "Advertisers do not receive access to unpublished editorial material and cannot purchase favorable coverage or ranking. Paid placements are selected by the advertising system and clearly labeled.",
        ],
      ],
    },
  },
  es: {
    about: {
      title: "Quiénes somos",
      lead: "Periodismo local independiente sobre entretenimiento y cultura en Texas.",
      sections: [
        [
          "Nuestra cobertura",
          "Informamos sobre música, cine, gastronomía, deportes, eventos y las personas que dan forma a la cultura local.",
        ],
        [
          "Nuestros idiomas",
          "El inglés es la edición principal. Una noticia en español se publica solo cuando existe una traducción revisada; nunca sustituimos silenciosamente el texto inglés.",
        ],
      ],
    },
    contact: {
      title: "Contacto",
      lead: "Envíe noticias, correcciones y consultas de colaboración a la redacción.",
      sections: [
        [
          "Redacción",
          "Utilice la dirección de contacto verificada que aparece abajo. No envíe contraseñas, datos de pago ni información personal sensible.",
        ],
      ],
    },
    "editorial-policy": {
      title: "Política editorial",
      lead: "Nuestro trabajo se guía por la precisión, las fuentes transparentes y la separación entre periodismo y publicidad.",
      sections: [
        [
          "Verificación y atribución",
          "Verificamos los hechos importantes, identificamos las fuentes cuando es seguro y enlazamos documentos primarios cuando están disponibles.",
        ],
        [
          "Trabajo asistido por IA",
          "La IA puede ayudar en búsquedas, resúmenes y flujos internos, pero no evita las reglas editoriales de publicación. El artículo canónico sigue siendo la fuente oficial.",
        ],
        [
          "Publicidad",
          "El contenido patrocinado y los anuncios se etiquetan y se mantienen separados de las decisiones editoriales.",
        ],
      ],
    },
    corrections: {
      title: "Política de correcciones",
      lead: "Corregimos los errores importantes con rapidez y mantenemos un registro responsable.",
      sections: [
        [
          "Cómo corregimos",
          "Las correcciones verificadas se aplican a la noticia canónica. Los cambios importantes actualizan la fecha de modificación y deben incluir una nota editorial.",
        ],
        [
          "Solicitar una corrección",
          "Incluya la URL, la afirmación cuestionada y las pruebas de respaldo al contactar con la redacción.",
        ],
      ],
    },
    ownership: {
      title: "Propiedad y financiación",
      lead: "Los lectores deben saber quién publica el sitio y cómo se gestionan las relaciones comerciales.",
      sections: [
        [
          "Editorial",
          "La publicación opera bajo la identidad editorial mostrada en este sitio. En producción deben publicarse el propietario legal y sus fuentes de financiación.",
        ],
        [
          "Independencia comercial",
          "Los anunciantes no acceden al material editorial no publicado y no pueden comprar cobertura favorable ni una mejor clasificación.",
        ],
      ],
    },
  },
} as const;

export function TrustPage({ data, path }: { data: Homepage; path: TrustPath }) {
  const language = data.language === "es" ? "es" : "en";
  const page = copy[language][path];
  const email = process.env.NEXT_PUBLIC_NEWSROOM_EMAIL;
  const legalName = process.env.NEXT_PUBLIC_PUBLISHER_LEGAL_NAME;
  const funding = process.env.NEXT_PUBLIC_FUNDING_DISCLOSURE;
  return (
    <>
      <SiteHeader
        portal={data.portal}
        language={language}
        alternates={Object.fromEntries(
          data.portal.supported_languages.map((item) => [
            item,
            `${data.portal.canonical_url}${item === data.portal.default_language ? "" : `/${item}`}/${path}`,
          ]),
        )}
      />
      <main className="page-width trust-page">
        <header>
          <p className="section-kicker">{data.portal.name}</p>
          <h1>{page.title}</h1>
          <p className="story-subtitle">{page.lead}</p>
        </header>
        {page.sections.map(([title, body]) => (
          <section key={title}>
            <h2>{title}</h2>
            <p>{body}</p>
          </section>
        ))}
        {path === "contact" ? (
          email ? (
            <p>
              <a href={`mailto:${email}`}>{email}</a>
            </p>
          ) : (
            <p className="trust-notice">
              {language === "es"
                ? "La dirección de la redacción se publicará antes del lanzamiento."
                : "The newsroom address will be published before launch."}
            </p>
          )
        ) : null}
        {path === "ownership" ? (
          legalName && funding ? (
            <dl className="publisher-facts">
              <div>
                <dt>
                  {language === "es" ? "Propietario legal" : "Legal owner"}
                </dt>
                <dd>{legalName}</dd>
              </div>
              <div>
                <dt>{language === "es" ? "Financiación" : "Funding"}</dt>
                <dd>{funding}</dd>
              </div>
            </dl>
          ) : (
            <p className="trust-notice">
              {language === "es"
                ? "Los datos legales y de financiación deben configurarse antes del lanzamiento."
                : "Legal ownership and funding details must be configured before launch."}
            </p>
          )
        ) : null}
      </main>
      <SiteFooter portal={data.portal} language={language} />
    </>
  );
}

export function AuthorPage({ data }: { data: AuthorPageData }) {
  return (
    <FeedView
      data={{
        portal: data.portal,
        feed: "latest",
        scope: data.name,
        label: data.name,
        language: data.language,
        canonical_url: data.canonical_url,
        alternates: data.alternates,
        items: data.items,
        next_cursor: null,
      }}
      title={data.name}
      deck={
        data.language === "es"
          ? `Artículos publicados por ${data.name}.`
          : `Published reporting by ${data.name}.`
      }
      path={new URL(data.canonical_url).pathname}
    />
  );
}
