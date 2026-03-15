/**
 * This configuration was generated using the CKEditor 5 Builder. You can modify it anytime using this link:
 * https://ckeditor.com/ckeditor-5/builder/#installation/NoNgNARATAdAjHGAGCkDMB2NBONAOPbAVgBZcpso04SQ8QM8ooik8kq5iQfKbMMJLBhCoIAUwB2qJGGBwws2QuUBdSACMNRbBoCGGiKqA===
 */

import {
	ClassicEditor,
	Autosave,
	Essentials,
	Paragraph,
	Autoformat,
	TextTransformation,
	LinkImage,
	Link,
	ImageBlock,
	ImageToolbar,
	BlockQuote,
	Bold,
	CKBox,
	CloudServices,
	ImageUpload,
	ImageInsert,
	ImageInsertViaUrl,
	AutoImage,
	PictureEditing,
	CKBoxImageEdit,
	TableColumnResize,
	Table,
	TableToolbar,
	Emoji,
	Mention,
	Heading,
	ImageTextAlternative,
	ImageCaption,
	ImageResize,
	ImageStyle,
	Indent,
	IndentBlock,
	ImageInline,
	Italic,
	ListProperties,
	List,
	MediaEmbed,
	PasteFromOffice,
	TableCaption,
	TableCellProperties,
	TableProperties,
	TodoList,
	Underline
} from 'ckeditor5';
import { AIChat, AIEditorIntegration, AIChatShortcuts, AIQuickActions, AIReviewMode, AITranslate } from 'ckeditor5-premium-features';

/**
 * Create a free account with a trial: https://portal.ckeditor.com/checkout?plan=free
 */
const LICENSE_KEY = '<YOUR_LICENSE_KEY>';

/**
 * Unique ID that will be used to identify this document. E.g. you may use ID taken from your database.
 * Read more: https://ckeditor.com/docs/ckeditor5/latest/api/module_collaboration-core_config-RealTimeCollaborationConfig.html
 */
const DOCUMENT_ID = '<YOUR_DOCUMENT_ID>';

/**
 * Please update the following values with your tokens.
 * Instructions on how to obtain them: https://ckeditor.com/docs/trial/latest/guides/real-time/quick-start.html
 */
const CLOUD_SERVICES_TOKEN_URL = '<YOUR_CLOUD_SERVICES_TOKEN_URL>';

const editorConfig = {
	toolbar: {
		items: [
			'undo',
			'redo',
			'|',
			'toggleAi',
			'aiQuickActions',
			'|',
			'heading',
			'|',
			'bold',
			'italic',
			'underline',
			'|',
			'emoji',
			'link',
			'insertImage',
			'ckbox',
			'mediaEmbed',
			'insertTable',
			'blockQuote',
			'|',
			'bulletedList',
			'numberedList',
			'todoList',
			'outdent',
			'indent'
		],
		shouldNotGroupWhenFull: false
	},
	plugins: [
		AIChat,
		AIChatShortcuts,
		AIEditorIntegration,
		AIQuickActions,
		AIReviewMode,
		AITranslate,
		Autoformat,
		AutoImage,
		Autosave,
		BlockQuote,
		Bold,
		CKBox,
		CKBoxImageEdit,
		CloudServices,
		Emoji,
		Essentials,
		Heading,
		ImageBlock,
		ImageCaption,
		ImageInline,
		ImageInsert,
		ImageInsertViaUrl,
		ImageResize,
		ImageStyle,
		ImageTextAlternative,
		ImageToolbar,
		ImageUpload,
		Indent,
		IndentBlock,
		Italic,
		Link,
		LinkImage,
		List,
		ListProperties,
		MediaEmbed,
		Mention,
		Paragraph,
		PasteFromOffice,
		PictureEditing,
		Table,
		TableCaption,
		TableCellProperties,
		TableColumnResize,
		TableProperties,
		TableToolbar,
		TextTransformation,
		TodoList,
		Underline
	],
	ai: {
		container: {
			type: 'overlay',
			side: 'right'
		},
		chat: {
			context: {
				document: {
					enabled: true
				},
				urls: {
					enabled: true
				},
				files: {
					enabled: true
				}
			},
			shortcuts: [
				/* See: https://ckeditor.com/docs/ckeditor5/latest/features/ai/ckeditor-ai-review.html#adding-extra-commands */
			]
		}
	},
	cloudServices: {
		tokenUrl: CLOUD_SERVICES_TOKEN_URL
	},
	collaboration: {
		channelId: DOCUMENT_ID
	},
	heading: {
		options: [
			{
				model: 'paragraph',
				title: 'Paragraph',
				class: 'ck-heading_paragraph'
			},
			{
				model: 'heading1',
				view: 'h1',
				title: 'Heading 1',
				class: 'ck-heading_heading1'
			},
			{
				model: 'heading2',
				view: 'h2',
				title: 'Heading 2',
				class: 'ck-heading_heading2'
			},
			{
				model: 'heading3',
				view: 'h3',
				title: 'Heading 3',
				class: 'ck-heading_heading3'
			},
			{
				model: 'heading4',
				view: 'h4',
				title: 'Heading 4',
				class: 'ck-heading_heading4'
			},
			{
				model: 'heading5',
				view: 'h5',
				title: 'Heading 5',
				class: 'ck-heading_heading5'
			},
			{
				model: 'heading6',
				view: 'h6',
				title: 'Heading 6',
				class: 'ck-heading_heading6'
			}
		]
	},
	image: {
		toolbar: [
			'toggleImageCaption',
			'imageTextAlternative',
			'|',
			'imageStyle:inline',
			'imageStyle:wrapText',
			'imageStyle:breakText',
			'|',
			'resizeImage',
			'|',
			'ckboxImageEdit'
		]
	},
	initialData:
		'<h2>Congratulations on setting up CKEditor 5! 🎉</h2>\n<p>\n\tYou\'ve successfully created a CKEditor 5 project. This powerful text editor\n\twill enhance your application, enabling rich text editing capabilities that\n\tare customizable and easy to use.\n</p>\n<h3>What\'s next?</h3>\n<ol>\n\t<li>\n\t\t<strong>Integrate into your app</strong>: time to bring the editing into\n\t\tyour application. Take the code you created and add to your application.\n\t</li>\n\t<li>\n\t\t<strong>Explore features:</strong> Experiment with different plugins and\n\t\ttoolbar options to discover what works best for your needs.\n\t</li>\n\t<li>\n\t\t<strong>Customize your editor:</strong> Tailor the editor\'s\n\t\tconfiguration to match your application\'s style and requirements. Or\n\t\teven write your plugin!\n\t</li>\n</ol>\n<p>\n\tKeep experimenting, and don\'t hesitate to push the boundaries of what you\n\tcan achieve with CKEditor 5. Your feedback is invaluable to us as we strive\n\tto improve and evolve. Happy editing!\n</p>\n<h3>Helpful resources</h3>\n<ul>\n\t<li>📝 <a href="https://portal.ckeditor.com/checkout?plan=free">Trial sign up</a>,</li>\n\t<li>📕 <a href="https://ckeditor.com/docs/ckeditor5/latest/installation/index.html">Documentation</a>,</li>\n\t<li>⭐️ <a href="https://github.com/ckeditor/ckeditor5">GitHub</a> (star us if you can!),</li>\n\t<li>🏠 <a href="https://ckeditor.com">CKEditor Homepage</a>,</li>\n\t<li>🧑‍💻 <a href="https://ckeditor.com/ckeditor-5/demo/">CKEditor 5 Demos</a>,</li>\n</ul>\n<h3>Need help?</h3>\n<p>\n\tSee this text, but the editor is not starting up? Check the browser\'s\n\tconsole for clues and guidance. It may be related to an incorrect license\n\tkey if you use premium features or another feature-related requirement. If\n\tyou cannot make it work, file a GitHub issue, and we will help as soon as\n\tpossible!\n</p>\n',
	licenseKey: LICENSE_KEY,
	link: {
		addTargetToExternalLinks: true,
		defaultProtocol: 'https://',
		decorators: {
			toggleDownloadable: {
				mode: 'manual',
				label: 'Downloadable',
				attributes: {
					download: 'file'
				}
			}
		}
	},
	list: {
		properties: {
			styles: true,
			startIndex: true,
			reversed: true
		}
	},
	mention: {
		feeds: [
			{
				marker: '@',
				feed: [
					/* See: https://ckeditor.com/docs/ckeditor5/latest/features/mentions.html */
				]
			}
		]
	},
	placeholder: 'Type or paste your content here!',
	table: {
		contentToolbar: ['tableColumn', 'tableRow', 'mergeTableCells', 'tableProperties', 'tableCellProperties']
	}
};

configUpdateAlert(editorConfig);

ClassicEditor.create(document.querySelector('#editor'), editorConfig);

/**
 * This function exists to remind you to update the config needed for premium features.
 * The function can be safely removed. Make sure to also remove call to this function when doing so.
 */
function configUpdateAlert(config) {
	if (configUpdateAlert.configUpdateAlertShown) {
		return;
	}

	const isModifiedByUser = (currentValue, forbiddenValue) => {
		if (currentValue === forbiddenValue) {
			return false;
		}

		if (currentValue === undefined) {
			return false;
		}

		return true;
	};

	const valuesToUpdate = [];

	configUpdateAlert.configUpdateAlertShown = true;

	if (!isModifiedByUser(config.licenseKey, '<YOUR_LICENSE_KEY>')) {
		valuesToUpdate.push('LICENSE_KEY');
	}

	if (!isModifiedByUser(config.cloudServices?.tokenUrl, '<YOUR_CLOUD_SERVICES_TOKEN_URL>')) {
		valuesToUpdate.push('CLOUD_SERVICES_TOKEN_URL');
	}

	if (valuesToUpdate.length) {
		window.alert(
			[
				'Please update the following values in your editor config',
				'to receive full access to Premium Features:',
				'',
				...valuesToUpdate.map(value => ` - ${value}`)
			].join('\n')
		);
	}
}
